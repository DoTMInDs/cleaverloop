from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from apps.accounts.models import User
from apps.credits.services import CreditService

@receiver(post_save, sender=User)
def user_post_save_handler(sender, instance, created, **kwargs):
    """Ensure every user gets a CreditWallet and receives starter credits."""
    if created:
        wallet = CreditService.get_or_create_wallet(instance)
        starter_credits = getattr(settings, 'DEFAULT_STARTER_CREDITS', 500)
        if not instance.starter_credits_granted and starter_credits > 0:
            CreditService.grant_credits(
                user=instance,
                amount=starter_credits,
                transaction_type='bonus',
                description='Welcome bonus starter credits'
            )
            instance.starter_credits_granted = True
            instance.save(update_fields=['starter_credits_granted'])
