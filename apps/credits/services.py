import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.credits.models import CreditWallet, CreditTransaction

logger = logging.getLogger(__name__)

class InsufficientCreditsError(Exception):
    """Raised when a wallet lacks enough balance for an operation."""
    pass

class CreditService:
    @staticmethod
    def get_or_create_wallet(user) -> CreditWallet:
        """Fetch or initialize a user's credit wallet."""
        wallet, created = CreditWallet.objects.get_or_create(user=user)
        return wallet

    @classmethod
    @transaction.atomic
    def grant_credits(
        cls,
        user,
        amount: int,
        transaction_type: str = 'bonus',
        description: str = 'Granted credits',
        external_reference: str = ''
    ) -> CreditTransaction:
        """Add credits to user's wallet with transaction record."""
        if amount <= 0:
            raise ValidationError("Grant amount must be greater than zero.")

        wallet = CreditWallet.objects.select_for_update().get_or_create(user=user)[0]
        bal_before = wallet.balance
        wallet.balance += amount
        wallet.lifetime_earned += amount
        bal_after = wallet.balance
        wallet.save(update_fields=['balance', 'lifetime_earned', 'updated_at'])

        tx = CreditTransaction.objects.create(
            wallet=wallet,
            amount=amount,
            transaction_type=transaction_type,
            balance_before=bal_before,
            balance_after=bal_after,
            description=description,
            external_reference=external_reference,
        )
        logger.info(f"Granted {amount} credits to {user.email}. New balance: {bal_after}")
        return tx

    @classmethod
    @transaction.atomic
    def reserve_credits(cls, user, estimated_credits: int, generation) -> CreditTransaction:
        """
        Atomically reserve credits for a generation job.
        Uses row-level locking (select_for_update) to prevent double spending.
        """
        if estimated_credits <= 0:
            return None

        wallet = CreditWallet.objects.select_for_update().get_or_create(user=user)[0]
        if wallet.balance < estimated_credits:
            raise InsufficientCreditsError(
                f"Insufficient credits. Required: {estimated_credits}, Available: {wallet.balance}."
            )

        bal_before = wallet.balance
        wallet.balance -= estimated_credits
        bal_after = wallet.balance
        wallet.save(update_fields=['balance', 'updated_at'])

        tx = CreditTransaction.objects.create(
            wallet=wallet,
            amount=-estimated_credits,
            transaction_type='generation_hold',
            generation=generation,
            balance_before=bal_before,
            balance_after=bal_after,
            description=f"Reserved hold for {generation.generation_type} ({generation.model_id_snapshot})",
        )
        generation.credits_reserved = estimated_credits
        generation.save(update_fields=['credits_reserved'])
        logger.info(f"Reserved {estimated_credits} credits for generation {generation.id} from {user.email}")
        return tx

    @classmethod
    @transaction.atomic
    def commit_credits(cls, generation, actual_credits: int = None) -> CreditTransaction:
        """
        Finalize consumption of credits upon successful generation.
        Adjusts difference if actual_credits differs from reserved.
        """
        user = generation.user
        reserved = generation.credits_reserved
        actual = actual_credits if actual_credits is not None else reserved

        wallet = CreditWallet.objects.select_for_update().get(user=user)
        wallet.lifetime_spent += actual
        wallet.save(update_fields=['lifetime_spent', 'updated_at'])

        difference = reserved - actual
        if difference > 0:
            # Reserved more than consumed, return difference
            wallet.balance += difference
            wallet.save(update_fields=['balance', 'updated_at'])
            CreditTransaction.objects.create(
                wallet=wallet,
                amount=difference,
                transaction_type='generation_refund',
                generation=generation,
                balance_before=wallet.balance - difference,
                balance_after=wallet.balance,
                description=f"Released unused hold difference for {generation.id}",
            )

        generation.credits_consumed = actual
        generation.save(update_fields=['credits_consumed'])

        # Record final consumption
        tx = CreditTransaction.objects.create(
            wallet=wallet,
            amount=0,  # Reserved hold already decremented wallet balance
            transaction_type='generation_consume',
            generation=generation,
            balance_before=wallet.balance,
            balance_after=wallet.balance,
            description=f"Settled {actual} credits for completed {generation.generation_type}",
        )
        return tx

    @classmethod
    @transaction.atomic
    def refund_credits(cls, generation, reason: str = "Generation failed") -> CreditTransaction:
        """
        Fully refund reserved credits back to user wallet if generation fails or cancels.
        """
        reserved = generation.credits_reserved
        if reserved <= 0:
            return None

        user = generation.user
        wallet = CreditWallet.objects.select_for_update().get(user=user)
        bal_before = wallet.balance
        wallet.balance += reserved
        bal_after = wallet.balance
        wallet.save(update_fields=['balance', 'updated_at'])

        generation.credits_reserved = 0
        generation.credits_consumed = 0
        generation.save(update_fields=['credits_reserved', 'credits_consumed'])

        tx = CreditTransaction.objects.create(
            wallet=wallet,
            amount=reserved,
            transaction_type='generation_refund',
            generation=generation,
            balance_before=bal_before,
            balance_after=bal_after,
            description=f"Refund: {reason}",
        )
        logger.info(f"Refunded {reserved} credits to {user.email} for generation {generation.id}")
        return tx
