from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

class CreditWallet(models.Model):
    """User credit wallet with atomic balance tracking."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance = models.BigIntegerField(default=0)
    lifetime_earned = models.BigIntegerField(default=0)
    lifetime_spent = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Credit Wallet'
        verbose_name_plural = 'Credit Wallets'

    def __str__(self):
        return f"{self.user.email} Wallet (Balance: {self.balance})"

    def clean(self):
        if self.balance < 0:
            raise ValidationError("Wallet balance cannot be negative.")

class CreditTransaction(models.Model):
    """Double-entry transactional audit record for every balance adjustment."""
    TRANSACTION_TYPES = [
        ('bonus', 'Bonus / Starter Credits'),
        ('subscription_credit', 'Monthly Subscription Credits'),
        ('purchase', 'Credit Pack Purchase'),
        ('generation_hold', 'Generation Reserved Hold'),
        ('generation_consume', 'Generation Final Consumption'),
        ('generation_refund', 'Generation Failure Refund'),
        ('adjustment', 'Administrative Adjustment'),
        ('expiration', 'Credit Expiration'),
    ]

    wallet = models.ForeignKey(
        CreditWallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    amount = models.BigIntegerField(
        help_text="Signed integer: positive for credit addition, negative for credit reduction"
    )
    transaction_type = models.CharField(max_length=32, choices=TRANSACTION_TYPES)
    generation = models.ForeignKey(
        'generations.Generation',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='credit_transactions'
    )
    balance_before = models.BigIntegerField()
    balance_after = models.BigIntegerField()
    description = models.CharField(max_length=255)
    external_reference = models.CharField(max_length=255, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'created_at']),
            models.Index(fields=['transaction_type']),
        ]

    def __str__(self):
        sign = "+" if self.amount > 0 else ""
        return f"[{self.get_transaction_type_display()}] {sign}{self.amount} -> {self.wallet.user.email} (Bal: {self.balance_after})"
