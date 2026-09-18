from django.urls import path
from apps.adminpanel import views

app_name = 'adminpanel'

urlpatterns = [
    path('', views.admin_dashboard_view, name='dashboard'),
    path('models/<int:model_id>/toggle/', views.toggle_model_status_view, name='toggle_model'),
    path('credits/adjust/', views.adjust_user_credits_view, name='adjust_credits'),
    path('diagnostics/api-health/', views.provider_health_diagnostics_view, name='api_health'),
]
