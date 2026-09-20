from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from apps.accounts.models import User

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom social account adapter for CleaverLoop AI:
    - Auto-links existing users by verified email to prevent duplicate account collisions.
    - Ensures username is safely set from email if not provided.
    - New users trigger user_post_save_handler signal to automatically provision
      a CreditWallet and 500 starter credits.
    """

    def pre_social_login(self, request, sociallogin):
        """
        If a user already exists with the email returned by Google/Apple,
        automatically connect the social account to the existing user.
        """
        if sociallogin.is_existing:
            return

        if not sociallogin.email_addresses:
            return

        email_address = sociallogin.email_addresses[0]
        # Only auto-link if the OAuth provider has verified this email address
        if not getattr(email_address, 'verified', False):
            return

        email = email_address.email.lower()
        try:
            existing_user = User.objects.get(email__iexact=email)
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            pass

    def populate_user(self, request, sociallogin, data):
        """Ensure username is cleanly initialized."""
        user = super().populate_user(request, sociallogin, data)
        if not user.username and user.email:
            user.username = user.email.split('@')[0]
        return user
