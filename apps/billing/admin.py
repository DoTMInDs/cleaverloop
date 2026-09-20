from django.contrib import admin
from apps.billing.models import SubscriptionPlan, Subscription

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'price_monthly',
        'credits_per_month',
        'badge_text',
        'paystack_plan_code',
        'can_access_premium_models',
        'is_active',
        'created_at',
    )
    list_editable = (
        'price_monthly',
        'credits_per_month',
        'can_access_premium_models',
        'is_active',
    )
    list_filter = ('is_active', 'can_access_premium_models')
    search_fields = ('name', 'slug', 'paystack_plan_code', 'description')
    ordering = ('price_monthly',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'plan',
        'status',
        'provider',
        'current_period_start',
        'current_period_end',
        'created_at',
    )
    list_filter = ('status', 'provider', 'plan')
    search_fields = ('user__email', 'user__username', 'external_subscription_id')
    raw_id_fields = ('user',)
