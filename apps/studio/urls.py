from django.urls import path
from apps.studio import views

app_name = 'studio'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('create/', views.CreateStudioView.as_view(), name='create'),
    path('explore/', views.ExploreView.as_view(), name='explore'),
]
