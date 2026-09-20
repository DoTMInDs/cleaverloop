from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Sum, Count
from django.http import HttpResponse

from apps.accounts.models import User
from apps.credits.models import CreditWallet, CreditTransaction
from apps.credits.services import CreditService
from apps.generations.models import Generation
from apps.providers.models import AIProviderConfig, AIModel
from apps.projects.models import Project

from apps.billing.models import SubscriptionPlan
from django.utils.text import slugify
from decimal import Decimal

@staff_member_required
def admin_dashboard_view(request):
    """Platform administration dashboard."""
    total_users = User.objects.count()
    total_generations = Generation.objects.count()
    failed_generations = Generation.objects.filter(status='failed').count()
    completed_generations = Generation.objects.filter(status='completed').count()
    
    total_credits_spent = CreditTransaction.objects.filter(
        transaction_type='generation_consume'
    ).count()

    providers = AIProviderConfig.objects.prefetch_related('models').all()
    recent_failures = Generation.objects.filter(status='failed').select_related('user', 'model', 'provider')[:10]
    plans = SubscriptionPlan.objects.all().order_by('price_monthly')
    free_plan = plans.filter(price_monthly=0).first()

    context = {
        'total_users': total_users,
        'total_generations': total_generations,
        'failed_generations': failed_generations,
        'completed_generations': completed_generations,
        'providers': providers,
        'recent_failures': recent_failures,
        'plans': plans,
        'free_plan': free_plan,
    }
    return render(request, 'adminpanel/dashboard.html', context)

@staff_member_required
@require_POST
def save_plan_view(request):
    """Create or update a subscription plan with custom price, credits, and features."""
    plan_id = request.POST.get('plan_id')
    name = request.POST.get('name', '').strip()
    slug = request.POST.get('slug', '').strip()
    price_monthly = request.POST.get('price_monthly', '0').strip()
    credits_per_month = request.POST.get('credits_per_month', '1000').strip()
    max_parallel_generations = request.POST.get('max_parallel_generations', '2').strip()
    can_access_premium_models = request.POST.get('can_access_premium_models') == 'on'
    is_active = request.POST.get('is_active') == 'on'
    features_raw = request.POST.get('features_raw', '')

    if not name:
        messages.error(request, "Plan name is required.")
        return redirect('adminpanel:dashboard')

    if not slug:
        slug = slugify(name)

    # Clean newline-separated features
    features = [line.strip() for line in features_raw.splitlines() if line.strip()]

    try:
        price_dec = Decimal(price_monthly)
        credits_int = int(credits_per_month)
        parallel_int = int(max_parallel_generations)
    except (ValueError, ArithmeticError):
        messages.error(request, "Invalid number entered for price, credits, or parallel generations.")
        return redirect('adminpanel:dashboard')

    if plan_id:
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        plan.name = name
        plan.slug = slug
        plan.price_monthly = price_dec
        plan.credits_per_month = credits_int
        plan.max_parallel_generations = parallel_int
        plan.can_access_premium_models = can_access_premium_models
        plan.is_active = is_active
        plan.features = features
        plan.save()
        messages.success(request, f"Updated plan '{plan.name}' successfully.")
    else:
        # Check slug uniqueness
        if SubscriptionPlan.objects.filter(slug=slug).exists():
            messages.error(request, f"A plan with slug '{slug}' already exists. Choose another.")
            return redirect('adminpanel:dashboard')

        plan = SubscriptionPlan.objects.create(
            name=name,
            slug=slug,
            price_monthly=price_dec,
            credits_per_month=credits_int,
            max_parallel_generations=parallel_int,
            can_access_premium_models=can_access_premium_models,
            is_active=is_active,
            features=features
        )
        messages.success(request, f"Created new plan '{plan.name}' successfully.")

    return redirect('adminpanel:dashboard')

@staff_member_required
@require_POST
def toggle_plan_status_view(request, plan_id):
    """Activate or deactivate a plan from being visible on the public pricing page."""
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    plan.is_active = not plan.is_active
    plan.save(update_fields=['is_active'])
    messages.success(request, f"Plan '{plan.name}' is now {'Active' if plan.is_active else 'Inactive'}.")
    return redirect('adminpanel:dashboard')

@staff_member_required
@require_POST
def update_starter_credits_view(request):
    """Adjust the default welcome starter credits granted to new user registrations."""
    amount_str = request.POST.get('starter_credits', '').strip()
    try:
        amount = int(amount_str)
        if amount < 0:
            raise ValueError()
    except ValueError:
        messages.error(request, "Starter credits must be a positive integer.")
        return redirect('adminpanel:dashboard')

    free_plan = SubscriptionPlan.objects.filter(price_monthly=0).first()
    if free_plan:
        free_plan.credits_per_month = amount
        # Update starter credit text in features list if present
        updated_features = []
        for feat in free_plan.features:
            if 'starter credit' in feat.lower():
                updated_features.append(f"{amount} Starter Credits")
            else:
                updated_features.append(feat)
        free_plan.features = updated_features
        free_plan.save()
    else:
        SubscriptionPlan.objects.create(
            name="Free Starter",
            slug="free-starter",
            price_monthly=0,
            credits_per_month=amount,
            features=[f"{amount} Starter Credits", "Access to Standard Models"],
            is_active=True
        )

    messages.success(request, f"Default starter credits for new signups successfully set to {amount}.")
    return redirect('adminpanel:dashboard')

@staff_member_required
@require_POST
def toggle_model_status_view(request, model_id):
    """Enable/disable a model dynamically without redeploying."""
    ai_model = get_object_or_404(AIModel, id=model_id)
    ai_model.is_enabled = not ai_model.is_enabled
    ai_model.save(update_fields=['is_enabled'])
    messages.success(request, f"Model '{ai_model.display_name}' is now {'Enabled' if ai_model.is_enabled else 'Disabled'}.")
    return redirect('adminpanel:dashboard')

@staff_member_required
@require_POST
def adjust_user_credits_view(request):
    """Manually grant or deduct credits for support and testing."""
    user_email = request.POST.get('user_email', '').strip()
    reason = request.POST.get('reason', 'Administrative adjustment')

    try:
        amount = int(request.POST.get('amount', 0))
    except (ValueError, TypeError):
        messages.error(request, "Please enter a valid integer for credit adjustment.")
        return redirect('adminpanel:dashboard')

    if amount == 0:
        messages.error(request, "Adjustment amount cannot be zero.")
        return redirect('adminpanel:dashboard')

    user = User.objects.filter(email=user_email).first()
    if not user:
        messages.error(request, f"User with email '{user_email}' not found.")
        return redirect('adminpanel:dashboard')

    try:
        if amount > 0:
            CreditService.grant_credits(
                user=user,
                amount=amount,
                transaction_type='adjustment',
                description=f"Admin Grant: {reason}"
            )
            messages.success(request, f"Successfully granted {amount} credits to {user_email}.")
        else:
            CreditService.deduct_credits(
                user=user,
                amount=abs(amount),
                transaction_type='adjustment',
                description=f"Admin Deduction: {reason}"
            )
            messages.success(request, f"Successfully deducted {abs(amount)} credits from {user_email}.")
    except Exception as exc:
        messages.error(request, f"Failed to adjust credits: {exc}")

    return redirect('adminpanel:dashboard')

from apps.providers.diagnostics import ProviderHealthChecker

@staff_member_required
def provider_health_diagnostics_view(request):
    """HTMX endpoint returning real-time billing and quota probes for all providers."""
    diagnostics = ProviderHealthChecker.check_all_providers()
    return render(request, 'adminpanel/partials/provider_diagnostics.html', {'diagnostics': diagnostics})

