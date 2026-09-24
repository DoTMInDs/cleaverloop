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
    def current_plan(self):
        """Safely fetch active SubscriptionPlan if available."""
        sub = getattr(self.user, 'subscription', None)
        if sub and sub.status == 'active' and sub.plan:
            return sub.plan
        return None

    @property
    def max_voice_profiles(self) -> int:
        """Returns maximum custom neural voice profiles allowed for this subscription tier (0 = unlimited)."""
        plan = self.current_plan
        if plan:
            return plan.max_voice_profiles
        tier_limits = {
            'free': 0,
            'starter': 3,
            'creator': 10,
            'ultra': 0,
        }
        return tier_limits.get(self.subscription_tier, 0)

    @property
    def can_clone_voices(self) -> bool:
        """Returns True if the user can create custom neural voice clones."""
        plan = self.current_plan
        if plan:
            return plan.can_clone_voices
        return self.subscription_tier in ('starter', 'creator', 'ultra')

    @property
    def voice_generation_cost(self) -> int:
        """Credit cost for generating speech audio / TTS."""
        plan = self.current_plan
        if plan:
            return plan.voice_generation_credit_cost
        costs = {
            'free': 25,
            'starter': 15,
            'creator': 10,
            'ultra': 5,
        }
        return costs.get(self.subscription_tier, 25)

    @property
    def voice_clone_cost(self) -> int:
        """Credit fee for cloning a new neural voice profile."""
        plan = self.current_plan
        if plan:
            return plan.voice_clone_credit_cost
        costs = {
            'free': 50,
            'starter': 50,
            'creator': 25,
            'ultra': 0,
        }
        return costs.get(self.subscription_tier, 50)

    @property
    def is_unlimited_eligible(self) -> bool:
        """Returns True if the user's subscription tier provides unlimited relaxed generations."""
        return self.subscription_tier in ('creator', 'ultra')

    @property
    def can_access_premium_models(self) -> bool:
        """Returns True if user plan permits accessing premium AI models (e.g. Veo 3.1 Cinema Master, Nano Banana Pro)."""
        plan = self.current_plan
        if plan:
            return getattr(plan, 'can_access_premium_models', False)
        return self.subscription_tier in ('creator', 'ultra')

    @property
    def default_video_model(self) -> str:
        """Returns the default/wired Veo video model for this subscription tier (Starter -> Lite, Creator -> Fast, Ultra -> Standard)."""
        if self.subscription_tier == 'starter':
            return 'veo-3.1-lite'
        elif self.subscription_tier == 'creator':
            return 'veo-3.1-fast'
        elif self.subscription_tier == 'ultra':
            return 'veo-3.1-standard'
        return 'veo-3.1-lite'

    @property
    def allowed_video_models(self) -> list:
        """Returns list of allowed video model_ids for user's subscription tier."""
        if self.subscription_tier == 'free':
            return []
        elif self.subscription_tier == 'starter':
            return ['veo-3.1-lite']
        elif self.subscription_tier == 'creator':
            return ['veo-3.1-lite', 'veo-3.1-fast', 'veo-3.1-standard']
        else: # ultra
            return ['veo-3.1-lite', 'veo-3.1-fast', 'veo-3.1-standard']

    def can_access_model(self, model_id: str) -> bool:
        """Enforces tier-based model wiring and access control."""
        if not model_id:
            return True
        m_id = model_id.lower()
        # Free users cannot generate video
        if self.subscription_tier == 'free' and ('veo' in m_id or 'video' in m_id):
            return False
        # Starter users are wired strictly to Veo Lite (lowest credit consumption)
        if self.subscription_tier == 'starter' and m_id in ('veo-3.1-fast', 'veo-3.1-standard'):
            return False
        # Premium model access check
        if m_id in ('veo-3.1-standard', 'nano-banana-pro') and not self.can_access_premium_models:
            return False
        return True

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
        constraints = [
            models.UniqueConstraint(
                fields=['external_reference'],
                condition=models.Q(external_reference__gt=''),
                name='unique_non_empty_external_reference'
            )
        ]

    def __str__(self):
        sign = "+" if self.amount > 0 else ""
        return f"[{self.get_transaction_type_display()}] {sign}{self.amount} -> {self.wallet.user.email} (Bal: {self.balance_after})"
