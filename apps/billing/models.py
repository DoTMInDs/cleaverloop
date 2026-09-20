import uuid
from django.db import models
from django.conf import settings

class SubscriptionPlan(models.Model):
    """Membership tiers defining monthly credit allowances, Paystack plans, and model access."""
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True)
    tagline = models.CharField(max_length=160, blank=True, help_text="Subtitle e.g. 'For creators making real AI videos'")
    badge_text = models.CharField(max_length=60, blank=True, help_text="Badge e.g. 'MOST POPULAR', '20% OFF'")
    description = models.TextField(blank=True)
    price_monthly = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    price_annually = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    credits_per_month = models.PositiveIntegerField(default=1000)
    max_parallel_generations = models.PositiveIntegerField(default=2)
    max_parallel_videos = models.PositiveIntegerField(default=2)
    max_parallel_images = models.PositiveIntegerField(default=2)
    max_characters = models.PositiveIntegerField(default=5, help_text="0 for unlimited")
    video_models_access = models.CharField(max_length=80, default="Standard only")
    has_all_models_access = models.BooleanField(default=False)
    has_unlimited_fast_models = models.BooleanField(default=False)
    has_early_access = models.BooleanField(default=False)
    has_priority_support = models.BooleanField(default=False)
    can_access_premium_models = models.BooleanField(default=False)
    paystack_plan_code = models.CharField(max_length=100, blank=True, help_text="Paystack Plan Code (e.g. PLN_xxx)")
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price_monthly']

    def __str__(self):
        return f"{self.name} (${self.price_monthly}/mo)"

    @classmethod
    def resolve_plan(cls, plan_id=None, slug=None, paystack_code=None):
        """Idempotently resolve a SubscriptionPlan by ID, slug, or Paystack plan code."""
        if plan_id:
            plan = cls.objects.filter(id=plan_id).first()
            if plan:
                return plan
        if slug:
            plan = cls.objects.filter(slug=slug).first()
            if plan:
                return plan
        if paystack_code:
            plan = cls.objects.filter(paystack_plan_code=paystack_code).first()
            if plan:
                return plan
        return None

class Subscription(models.Model):
    """Active user subscription status."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('canceled', 'Canceled'),
        ('trialing', 'Trialing'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscribers'
    )
    provider = models.CharField(max_length=50, default='paystack')
    customer_code = models.CharField(max_length=100, blank=True, db_index=True)
    external_subscription_id = models.CharField(max_length=255, blank=True, db_index=True)
    email_token = models.CharField(max_length=100, blank=True)
    last_payment_reference = models.CharField(max_length=100, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"
