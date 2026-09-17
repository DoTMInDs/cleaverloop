from django.urls import path
from apps.credits import views

app_name = 'credits'

urlpatterns = [
    path('wallet/', views.WalletDetailView.as_view(), name='wallet'),
    path('badge/', views.live_credit_badge, name='badge'),
]
