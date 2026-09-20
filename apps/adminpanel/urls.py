from django.urls import path
from apps.adminpanel import views

app_name = 'adminpanel'

urlpatterns = [
    path('', views.admin_dashboard_view, name='dashboard'),
    path('models/<int:model_id>/toggle/', views.toggle_model_status_view, name='toggle_model'),
    path('credits/adjust/', views.adjust_user_credits_view, name='adjust_credits'),
    path('credits/starter-amount/', views.update_starter_credits_view, name='update_starter_credits'),
    path('plans/save/', views.save_plan_view, name='save_plan'),
    path('plans/<int:plan_id>/toggle/', views.toggle_plan_status_view, name='toggle_plan'),
    path('diagnostics/api-health/', views.provider_health_diagnostics_view, name='api_health'),
]
