from django.shortcuts import render
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.billing.models import SubscriptionPlan, Subscription

class PricingPlansView(ListView):
    model = SubscriptionPlan
    template_name = 'billing/plans.html'
    context_object_name = 'plans'

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True)

class SubscriptionPortalView(LoginRequiredMixin, ListView):
    template_name = 'billing/portal.html'
    model = SubscriptionPlan

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['subscription'] = getattr(self.request.user, 'subscription', None)
        return ctx
