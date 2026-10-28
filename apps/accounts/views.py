import hashlib
import json
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.views.generic import CreateView, TemplateView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from apps.accounts.forms import UserRegisterForm, UserLoginForm


class RegisterView(CreateView):
    form_class = UserRegisterForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('studio:dashboard')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            from apps.billing.models import SubscriptionPlan
            from django.conf import settings
            free_plan = SubscriptionPlan.objects.filter(is_active=True, price_monthly=0).first()
            ctx['starter_credits'] = free_plan.credits_per_month if free_plan else getattr(settings, 'DEFAULT_STARTER_CREDITS', 500)
        except Exception:
            ctx['starter_credits'] = 500
        return ctx

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in self.request.headers.get('Accept', ''):
            return JsonResponse({'success': True, 'redirect_url': str(self.success_url)})
        return redirect(self.success_url)

    def form_invalid(self, form):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in self.request.headers.get('Accept', ''):
            errors = []
            for field, err_list in form.errors.items():
                for err in err_list:
                    errors.append(str(err))
            return JsonResponse({
                'success': False,
                'errors': errors,
                'error_message': errors[0] if errors else 'Please correct the errors below.'
            }, status=400)
        return super().form_invalid(form)


class LoginView(DjangoLoginView):
    form_class = UserLoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        super().form_valid(form)
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in self.request.headers.get('Accept', ''):
            return JsonResponse({'success': True, 'redirect_url': self.get_success_url()})
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in self.request.headers.get('Accept', ''):
            errors = []
            for field, err_list in form.errors.items():
                for err in err_list:
                    errors.append(str(err))
            return JsonResponse({
                'success': False,
                'errors': errors,
                'error_message': errors[0] if errors else 'Invalid email or password.'
            }, status=400)
        return super().form_invalid(form)


def logout_view(request):
    logout(request)
    return redirect('accounts:login')


def generate_user_referral_code(user) -> str:
    """Generate a consistent, human-friendly 6-character alphanumeric code for a user."""
    seed = f"cleaverloop_referral_{user.id}_{user.email}"
    digest = hashlib.sha256(seed.encode('utf-8')).hexdigest()
    charset = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    num = int(digest[:12], 16)
    code_chars = []
    for _ in range(6):
        code_chars.append(charset[num % len(charset)])
        num //= len(charset)
    return "".join(code_chars)


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Subscription details
        subscription = getattr(user, 'subscription', None)
        plan_name = "Free"
        if subscription and subscription.status == 'active' and subscription.plan:
            plan_name = subscription.plan.name

        referral_code = generate_user_referral_code(user)
        referral_code_spaced = " ".join(list(referral_code))

        from apps.accounts.models import ReferralRedemption
        from django.db.models import Sum
        referrals_qs = ReferralRedemption.objects.filter(referrer=user)
        referrals_count = referrals_qs.count()
        earned_credits = referrals_qs.aggregate(total=Sum('credits_awarded'))['total'] or 0
        has_redeemed_referral = ReferralRedemption.objects.filter(referee=user).exists()

        context.update({
            'subscription': subscription,
            'plan_name': plan_name,
            'referral_code': referral_code,
            'referral_code_spaced': referral_code_spaced,
            'referrals_count': referrals_count,
            'earned_credits': earned_credits,
            'has_redeemed_referral': has_redeemed_referral,
        })
        return context


@login_required
@require_POST
def redeem_referral_code_view(request):
    """Validates and redeems a 6-character creator referral code, awarding 1,000 bonus credits to both users."""
    from apps.accounts.models import User, ReferralRedemption
    from apps.credits.services import CreditService
    from django.db import transaction

    try:
        if request.content_type and 'application/json' in request.content_type:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            raw_code = payload.get('code', '')
        else:
            raw_code = request.POST.get('code', '')
    except Exception:
        raw_code = request.POST.get('code', '')

    code = "".join(str(raw_code).strip().upper().split())
    if len(code) < 4:
        return JsonResponse({'success': False, 'error': 'Please enter a valid 6-character referral code.'}, status=400)

    user = request.user
    if ReferralRedemption.objects.filter(referee=user).exists():
        return JsonResponse({'success': False, 'error': 'You have already redeemed a referral code on this account.'}, status=400)

    own_code = generate_user_referral_code(user)
    if code == own_code:
        return JsonResponse({'success': False, 'error': 'You cannot redeem your own referral code.'}, status=400)

    referrer = None
    for candidate in User.objects.exclude(id=user.id).only('id', 'email'):
        if generate_user_referral_code(candidate) == code:
            referrer = candidate
            break

    if not referrer:
        return JsonResponse({'success': False, 'error': 'Referral code not found. Please check the code and try again.'}, status=404)

    reward_amount = 1000
    with transaction.atomic():
        ReferralRedemption.objects.create(
            referrer=referrer,
            referee=user,
            code_used=code,
            credits_awarded=reward_amount,
        )
        referee_tx = CreditService.grant_credits(
            user=user,
            amount=reward_amount,
            transaction_type='bonus',
            description=f'Referral bonus unlocked with code {code}',
            external_reference=f'referral:referee:{user.id}',
        )
        CreditService.grant_credits(
            user=referrer,
            amount=reward_amount,
            transaction_type='bonus',
            description=f'Referral reward: {user.email} redeemed your code {code}',
            external_reference=f'referral:referrer:{referrer.id}:{user.id}',
        )

    return JsonResponse({
        'success': True,
        'credits_added': reward_amount,
        'new_balance': referee_tx.balance_after,
        'message': f'{reward_amount:,} bonus credits unlocked!',
    })
