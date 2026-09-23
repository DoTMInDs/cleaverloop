from django.urls import path
from apps.voices import views

app_name = 'voices'

urlpatterns = [
    path('', views.VoiceListView.as_view(), name='list'),
    path('create/', views.VoiceCreateView.as_view(), name='create'),
    path('<uuid:pk>/', views.VoiceDetailView.as_view(), name='detail'),
    path('<uuid:pk>/delete/', views.VoiceDeleteView.as_view(), name='delete'),
    path('api/preview/', views.api_preview_speech, name='api_preview'),
]
