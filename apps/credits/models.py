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
    SUBSCRIPTION_TIERS = [
        ('free', 'Free Starter (500 Credits)'),
        ('starter', 'Starter (90,000 Credits/mo)'),
        ('creator', 'Creator (400,000 Credits/mo + Unlimited)'),
        ('ultra', 'Ultra (1,000,000 Credits/mo + Unlimited)'),
    ]

    subscription_tier = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_TIERS,
        default='free',
        db_index=True
    )
    subscription_credits = models.BigIntegerField(default=500, help_text="Monthly refreshing credits")
    purchased_credits = models.BigIntegerField(default=0, help_text="Non-expiring top-up credits")
    subscription_renewal_date = models.DateTimeField(null=True, blank=True)
    balance = models.BigIntegerField(default=0)
    lifetime_earned = models.BigIntegerField(default=0)
    lifetime_spent = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Credit Wallet'
        verbose_name_plural = 'Credit Wallets'

    def __str__(self):
        tier_label = dict(self.SUBSCRIPTION_TIERS).get(self.subscription_tier, self.subscription_tier)
        return f"{self.user.email} Wallet [{tier_label}] (Balance: {self.balance})"

    @property
    def max_parallel_generations(self) -> int:
        """Returns maximum simultaneous generation jobs allowed for this subscription tier."""
        limits = {
            'free': 1,
            'starter': 2,
            'creator': 4,
            'ultra': 8,
        }
        return limits.get(self.subscription_tier, 1)

    @property
    def is_unlimited_eligible(self) -> bool:
        """Returns True if the user's subscription tier provides unlimited relaxed generations."""
        return self.subscription_tier in ('creator', 'ultra')

    @property
    def in_relaxed_mode(self) -> bool:
        """Returns True if user has exhausted priority credits but is eligible for unlimited relaxed generations."""
        return self.is_unlimited_eligible and self.balance <= 0

    @property
    def formatted_balance(self) -> str:
        """Human-friendly credit balance string (e.g. '500', '90K', '400K', '1M')."""
        bal = self.balance
        if bal >= 1_000_000:
            return f"{bal / 1_000_000:.1f}M".replace('.0M', 'M')
        elif bal >= 10_000:
            return f"{bal / 1_000:.0f}K"
        elif bal >= 1_000:
            return f"{bal / 1_000:.1f}K".replace('.0K', 'K')
        return f"{bal:,}"

    def clean(self):
        if self.balance < 0 and not self.is_unlimited_eligible:
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
