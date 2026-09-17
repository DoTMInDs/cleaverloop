def credit_wallet(request):
    """Inject current user's credit wallet and balance into template context."""
    if request.user.is_authenticated:
        # Access through related_name 'wallet'
        wallet = getattr(request.user, 'wallet', None)
        if wallet is None:
            from apps.credits.services import CreditService
            wallet = CreditService.get_or_create_wallet(request.user)
        return {
            'user_wallet': wallet,
            'credit_balance': wallet.balance,
        }
    return {
        'user_wallet': None,
        'credit_balance': 0,
    }
