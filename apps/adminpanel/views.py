from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Sum, Count
from django.http import HttpResponse

from apps.accounts.models import User
from apps.credits.models import CreditWallet, CreditTransaction
from apps.credits.services import CreditService
from apps.generations.models import Generation
from apps.providers.models import AIProviderConfig, AIModel
from apps.projects.models import Project

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

    context = {
        'total_users': total_users,
        'total_generations': total_generations,
        'failed_generations': failed_generations,
        'completed_generations': completed_generations,
        'providers': providers,
        'recent_failures': recent_failures,
    }
    return render(request, 'adminpanel/dashboard.html', context)

@staff_member_required
def toggle_model_status_view(request, model_id):
    """Enable/disable a model dynamically without redeploying."""
    ai_model = get_object_or_404(AIModel, id=model_id)
    ai_model.is_enabled = not ai_model.is_enabled
    ai_model.save(update_fields=['is_enabled'])
    messages.success(request, f"Model '{ai_model.display_name}' is now {'Enabled' if ai_model.is_enabled else 'Disabled'}.")
    return redirect('adminpanel:dashboard')

@staff_member_required
def adjust_user_credits_view(request):
    """Manually grant or deduct credits for support and testing."""
    if request.method == 'POST':
        user_email = request.POST.get('user_email', '').strip()
        amount = int(request.POST.get('amount', 0))
        reason = request.POST.get('reason', 'Administrative adjustment')

        user = User.objects.filter(email=user_email).first()
        if not user:
            messages.error(request, f"User with email '{user_email}' not found.")
            return redirect('adminpanel:dashboard')

        CreditService.grant_credits(
            user=user,
            amount=amount,
            transaction_type='adjustment',
            description=f"Admin: {reason}"
        )
        messages.success(request, f"Successfully adjusted {amount} credits for {user_email}.")
    return redirect('adminpanel:dashboard')
