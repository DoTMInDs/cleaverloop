from django.urls import path
from apps.billing import views, webhooks

app_name = 'billing'

urlpatterns = [
    path('plans/', views.PricingPlansView.as_view(), name='plans'),
    path('checkout/<int:plan_id>/', views.InitializeCheckoutView.as_view(), name='checkout'),
    path('callback/', views.PaymentCallbackView.as_view(), name='callback'),
    path('portal/', views.SubscriptionPortalView.as_view(), name='portal'),
    path('cancel/', views.CancelSubscriptionView.as_view(), name='cancel'),
    path('webhook/paystack/', webhooks.paystack_webhook_view, name='webhook'),
]
