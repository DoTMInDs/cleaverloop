from django.shortcuts import render
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from apps.credits.models import CreditTransaction
from apps.credits.services import CreditService

class WalletDetailView(LoginRequiredMixin, ListView):
    model = CreditTransaction
    template_name = 'credits/wallet.html'
    context_object_name = 'transactions'
    paginate_by = 25

    def get_queryset(self):
        wallet = CreditService.get_or_create_wallet(self.request.user)
        return wallet.transactions.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['wallet'] = CreditService.get_or_create_wallet(self.request.user)
        return ctx

def live_credit_badge(request):
    """HTMX endpoint to refresh navbar credit balance pill."""
    if not request.user.is_authenticated:
        return HttpResponse("")
    wallet = CreditService.get_or_create_wallet(request.user)
    return render(request, 'partials/credit_badge.html', {'user_wallet': wallet, 'credit_balance': wallet.balance})
