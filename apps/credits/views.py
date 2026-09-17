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

from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

@login_required
@require_POST
def quick_refill_credits_view(request):
    """Developer / User 1-click refill to prevent credit starvation during creative testing."""
    amount = 1000
    CreditService.grant_credits(
        request.user,
        amount=amount,
        transaction_type='bonus',
        description='Quick Dev Credit Refill (+1000)'
    )
    wallet = CreditService.get_or_create_wallet(request.user)
    
    html = f"""
    <div hx-swap-oob="true" id="credit-badge-container">
        <a href="/credits/wallet/" class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface border border-white/10 hover:border-brand-500/50 transition">
            <span class="text-amber-400 font-bold text-xs">🪙</span>
            <span class="font-bold text-xs text-white">{wallet.balance}</span>
            <span class="text-[10px] text-slate-400">CR</span>
        </a>
    </div>
    <div class="glass-panel rounded-2xl p-4 border border-emerald-500/30 bg-emerald-950/40 text-emerald-200 flex items-center justify-between">
        <div class="flex items-center gap-2 text-xs font-semibold text-emerald-300">
            <span>✓ Added {amount} credits successfully! New balance: <strong>{wallet.balance}</strong> credits.</span>
        </div>
        <span class="text-[11px] text-emerald-400 font-mono">Ready to Generate</span>
    </div>
    """
    return HttpResponse(html)
