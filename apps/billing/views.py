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

from django.core.cache import cache

class PricingPlansView(ListView):
    """Render public pricing page with 3 core tiers, Free tier callout, and feature matrix."""
    model = SubscriptionPlan
    template_name = 'billing/plans.html'
    context_object_name = 'plans'

    def get_queryset(self):
        cached = cache.get('active_subscription_plans')
        if cached is not None:
            return cached
        plans = list(SubscriptionPlan.objects.filter(is_active=True).order_by('price_monthly'))
        cache.set('active_subscription_plans', plans, timeout=1800)
        return plans

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

class InitializeTopupCheckoutView(LoginRequiredMixin, View):
    """Initiate Paystack Mobile Money / Card checkout for top-up credit packs."""
    TOPUP_PACKS = {
        'pack-50k': {'credits': 50000, 'price_usd': 10.00, 'name': 'Starter Pack (50K)'},
        'pack-250k': {'credits': 250000, 'price_usd': 45.00, 'name': 'Creator Pack (250K)'},
        'pack-600k': {'credits': 600000, 'price_usd': 99.00, 'name': 'Studio Pack (600K)'},
    }

    def post(self, request, pack_id):
        pack = self.TOPUP_PACKS.get(pack_id)
        if not pack:
            messages.error(request, "Invalid credit pack selected.")
            return redirect('billing:plans')

        callback_url = request.build_absolute_uri(reverse('billing:callback'))
        res = PaystackService.initialize_topup_transaction(
            user=request.user,
            pack_id=pack_id,
            credits_amount=pack['credits'],
            price_usd=pack['price_usd'],
            callback_url=callback_url
        )

        if res.get('status') and res.get('data', {}).get('authorization_url'):
            return redirect(res['data']['authorization_url'])
        else:
            err = res.get('message', 'Unable to initiate Mobile Money / Card checkout.')
            messages.error(request, f"Payment error: {err}")
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
        metadata = v_data.get('metadata', {}) if isinstance(v_data.get('metadata'), dict) else {}

        # Enforce IDOR protection: if user_id was stored in transaction metadata, verify it matches request.user
        tx_user_id = str(metadata.get('user_id', '')).strip()
        customer_email = v_data.get('customer', {}).get('email', '').strip().lower()

        if tx_user_id and tx_user_id != str(request.user.id):
            logger.error(
                f"IDOR attempt blocked: User {request.user.id} ({request.user.email}) "
                f"attempted to claim reference '{reference}' belonging to User {tx_user_id}."
            )
            messages.error(request, "Access denied: This payment transaction belongs to another account.")
            return redirect('billing:plans')

        # In live production mode, verify customer email matches the authenticated user
        if not PaystackService.is_mock_mode() and customer_email and customer_email != request.user.email.lower():
            logger.error(
                f"Email mismatch: User {request.user.email} attempted to claim payment for {customer_email} (ref: {reference})"
            )
            messages.error(request, "Access denied: Payment email does not match your active account.")
            return redirect('billing:plans')

        # Check for top-up credit pack purchase
        pack_id = metadata.get('pack_id')
        if metadata.get('payment_type') == 'topup' or pack_id in InitializeTopupCheckoutView.TOPUP_PACKS:
            pack = InitializeTopupCheckoutView.TOPUP_PACKS.get(pack_id)
            if pack:
                credits_to_grant = pack['credits']
            else:
                try:
                    credits_to_grant = int(metadata.get('credits_amount') or 50000)
                except (ValueError, TypeError):
                    credits_to_grant = 50000

            external_ref = f"paystack:topup:{reference}"

            if not CreditTransaction.objects.filter(external_reference=external_ref).exists():
                try:
                    from django.db import IntegrityError
                    CreditService.grant_credits(
                        user=request.user,
                        amount=credits_to_grant,
                        transaction_type='purchase',
                        description=f"Top-up credit pack purchase ({credits_to_grant:,} credits)",
                        external_reference=external_ref
                    )
                    messages.success(request, f"🎉 Added {credits_to_grant:,} top-up credits to your wallet via Mobile Money / Card!")
                except IntegrityError:
                    messages.info(request, "Top-up credits already applied to your account.")
            else:
                messages.info(request, "Top-up credits already applied to your account.")
            return redirect('credits:wallet')

        # Resolve plan (prioritize verified metadata over untrusted GET parameter)
        plan = SubscriptionPlan.resolve_plan(
            plan_id=metadata.get('plan_id') or plan_id,
            slug=metadata.get('plan_slug'),
            paystack_code=v_data.get('plan')
        )
        if not plan and metadata.get('plan_id'):
            plan = SubscriptionPlan.resolve_plan(plan_id=metadata['plan_id'])
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

        # Atomically activate subscription, update wallet tier, and grant credits
        CreditService.activate_subscription(
            user=request.user,
            plan=plan,
            reference=reference,
            customer_code=v_data.get('customer', {}).get('customer_code', ''),
            external_subscription_id=v_data.get('plan', '') or v_data.get('subscription_code', ''),
            grant_monthly_credits=True
        )
        messages.success(
            request,
            f"🎉 Welcome to {plan.name}! {plan.credits_per_month:,} credits have been added to your wallet."
        )

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
        ctx['usd_to_ghs_rate'] = CurrencyService.get_usd_to_ghs_rate()
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
