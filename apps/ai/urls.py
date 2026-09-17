from django.urls import path
from apps.ai import views

app_name = 'agent'

urlpatterns = [
    path('', views.super_agent_page_view, name='studio'),
    path('plan/', views.plan_agent_brief_view, name='plan'),
    path('execute/', views.execute_agent_plan_view, name='execute'),
]
