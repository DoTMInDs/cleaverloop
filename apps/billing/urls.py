from django.urls import path
from apps.billing import views

app_name = 'billing'

urlpatterns = [
    path('plans/', views.PricingPlansView.as_view(), name='plans'),
    path('portal/', views.SubscriptionPortalView.as_view(), name='portal'),
]
