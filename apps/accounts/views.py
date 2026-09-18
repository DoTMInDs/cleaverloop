from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.views.generic import CreateView, TemplateView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.accounts.forms import UserRegisterForm, UserLoginForm

from django.http import JsonResponse

class RegisterView(CreateView):
    form_class = UserRegisterForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('studio:dashboard')

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

import hashlib

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

        context.update({
            'subscription': subscription,
            'plan_name': plan_name,
            'referral_code': referral_code,
            'referral_code_spaced': referral_code_spaced,
            'referrals_count': 0,
            'earned_credits': 0,
        })
        return context

