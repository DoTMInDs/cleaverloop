import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

from apps.billing.models import SubscriptionPlan, Subscription
from apps.billing.paystack import PaystackService, CurrencyService
from apps.credits.models import CreditTransaction
from apps.credits.services import CreditService

logger = logging.getLogger(__name__)

class PricingPlansView(ListView):
    """Render public pricing page with 3 core tiers, Free tier callout, and feature matrix."""
    model = SubscriptionPlan
    template_name = 'billing/plans.html'
    context_object_name = 'plans'

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True).order_by('price_monthly')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_plans = list(self.get_queryset())
        ctx['free_plan'] = next((p for p in all_plans if p.price_monthly == 0), None)
        # Paid tiers to display as prominent cards: Starter ($15), Creator ($45), Ultra ($75)
        ctx['paid_plans'] = [p for p in all_plans if p.price_monthly > 0]
        ctx['starter_plan'] = next((p for p in all_plans if p.slug == 'starter'), None)
        ctx['creator_plan'] = next((p for p in all_plans if p.slug == 'creator'), None)
        ctx['ultra_plan'] = next((p for p in all_plans if p.slug == 'ultra'), None)
        
        ctx['usd_to_ghs_rate'] = CurrencyService.get_usd_to_ghs_rate()

        if self.request.user.is_authenticated:
            ctx['current_subscription'] = getattr(self.request.user, 'subscription', None)
            ctx['wallet'] = CreditService.get_or_create_wallet(self.request.user)
        else:
            ctx['current_subscription'] = None
            ctx['wallet'] = None
        return ctx

class InitializeCheckoutView(LoginRequiredMixin, View):
    """Initiate Paystack checkout session for the selected subscription tier."""
    def post(self, request, plan_id):
        plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)

        if plan.price_monthly <= 0:
            messages.info(request, "You are already on the Free Starter plan.")
            return redirect('billing:plans')

        current_sub = getattr(request.user, 'subscription', None)
        if current_sub and current_sub.status == 'active' and current_sub.plan_id == plan.id:
            messages.info(request, f"You are already on the {plan.name} plan.")
            return redirect('billing:portal')

        callback_url = request.build_absolute_uri(reverse('billing:callback'))
        # Include plan_id in callback for fallback resolution
        if '?' in callback_url:
            callback_url += f"&plan_id={plan.id}"
        else:
            callback_url += f"?plan_id={plan.id}"

        res = PaystackService.initialize_transaction(
            user=request.user,
            plan=plan,
            callback_url=callback_url
        )

        if res.get('status') and res.get('data', {}).get('authorization_url'):
            return redirect(res['data']['authorization_url'])
        else:
            err_msg = res.get('message', 'Unable to initiate payment with Paystack.')
            messages.error(request, f"Payment error: {err_msg}")
            return redirect('billing:plans')

class PaymentCallbackView(LoginRequiredMixin, View):
    """Handle redirect back from Paystack checkout, verify transaction, and grant credits."""
    def get(self, request):
        reference = request.GET.get('reference') or request.GET.get('trxref')
        plan_id = request.GET.get('plan_id')

        if not reference:
            messages.error(request, "No transaction reference provided by payment processor.")
            return redirect('billing:plans')

        # Verify transaction with Paystack
        verification = PaystackService.verify_transaction(reference)

        if not verification.get('status') or verification.get('data', {}).get('status') != 'success':
            messages.error(request, "Payment verification unsuccessful or declined.")
            return redirect('billing:plans')

        v_data = verification.get('data', {})

        # Resolve plan
        plan = SubscriptionPlan.resolve_plan(
            plan_id=plan_id,
            slug=v_data.get('metadata', {}).get('plan_slug') if isinstance(v_data.get('metadata'), dict) else None,
            paystack_code=v_data.get('plan')
        )
        if not plan and isinstance(v_data.get('metadata'), dict) and v_data.get('metadata', {}).get('plan_id'):
            plan = SubscriptionPlan.resolve_plan(plan_id=v_data['metadata']['plan_id'])
        if not plan:
            # Fallback to Creator plan if unspecified
            plan = SubscriptionPlan.objects.filter(slug='creator').first() or SubscriptionPlan.objects.filter(price_monthly__gt=0).first()

        # In live mode, ensure the verified transaction amount matches or exceeds plan price
        if not PaystackService.is_mock_mode() and plan and plan.price_monthly > 0:
            paid_amount = v_data.get('amount')
            from django.conf import settings
            currency = getattr(settings, 'PAYSTACK_CURRENCY', 'GHS')
            if currency.upper() == 'GHS':
                expected_ghs, _ = CurrencyService.convert_usd_to_ghs(plan.price_monthly)
                expected_amount = int(round(expected_ghs * 100))
            else:
                expected_amount = int(plan.price_monthly * 100)

            # Allow 5% tolerance for minor exchange rate variations or plan-matched pricing
            if paid_amount is not None and paid_amount < (expected_amount * 0.95):
                logger.warning(
                    f"Payment amount mismatch for user {request.user.id}: paid {paid_amount}, expected {expected_amount}"
                )
                messages.error(request, "Payment verification error: Paid amount does not match plan price.")
                return redirect('billing:plans')

        external_ref = f"paystack:{reference}"

        # Idempotent credit grant: check if already processed
        if not CreditTransaction.objects.filter(external_reference=external_ref).exists():
            # Activate or update subscription
            sub, _ = Subscription.objects.update_or_create(
                user=request.user,
                defaults={
                    'plan': plan,
                    'provider': 'paystack',
                    'status': 'active',
                    'last_payment_reference': reference,
                    'customer_code': v_data.get('customer', {}).get('customer_code', ''),
                    'external_subscription_id': v_data.get('plan', '') or v_data.get('subscription_code', ''),
                }
            )

            # Atomically grant credits to wallet
            CreditService.grant_credits(
                user=request.user,
                amount=plan.credits_per_month,
                transaction_type='subscription_credit',
                description=f"Paystack monthly subscription credits ({plan.name})",
                external_reference=external_ref
            )
            messages.success(
                request,
                f"🎉 Welcome to {plan.name}! {plan.credits_per_month:,} credits have been added to your wallet."
            )
        else:
            messages.info(request, "Payment already verified and credits applied.")

        return redirect('billing:portal')

class SubscriptionPortalView(LoginRequiredMixin, TemplateView):
    """Customer subscription portal displaying active plan, credit balance, and options."""
    template_name = 'billing/portal.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['subscription'] = getattr(self.request.user, 'subscription', None)
        ctx['wallet'] = CreditService.get_or_create_wallet(self.request.user)
        ctx['recent_transactions'] = CreditTransaction.objects.filter(
            wallet=ctx['wallet']
        ).order_by('-created_at')[:10]
        ctx['plans'] = SubscriptionPlan.objects.filter(is_active=True).order_by('price_monthly')
        return ctx

@method_decorator(require_POST, name='dispatch')
class CancelSubscriptionView(LoginRequiredMixin, View):
    """Allows subscriber to cancel active recurring subscription."""
    def post(self, request):
        sub = getattr(request.user, 'subscription', None)
        if not sub or sub.status != 'active':
            messages.info(request, "You do not have an active subscription.")
            return redirect('billing:portal')

        # Disable on Paystack if codes are present
        if sub.external_subscription_id and sub.email_token:
            PaystackService.disable_subscription(sub.external_subscription_id, sub.email_token)

        sub.status = 'canceled'
        sub.save(update_fields=['status'])

        messages.info(request, "Your subscription has been canceled. You retain your existing credit balance.")
        return redirect('billing:portal')
