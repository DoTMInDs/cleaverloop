def credit_wallet(request):
    """Inject current user's credit wallet and balance into template context with request-level memoization."""
    if request.user.is_authenticated:
        wallet = getattr(request, '_cached_wallet', None)
        if wallet is None:
            wallet = getattr(request.user, 'wallet', None)
            if wallet is None:
                from apps.credits.services import CreditService
                wallet = CreditService.get_or_create_wallet(request.user)
            request._cached_wallet = wallet
        return {
            'user_wallet': wallet,
            'credit_balance': wallet.balance,
        }
    return {
        'user_wallet': None,
        'credit_balance': 0,
    }
