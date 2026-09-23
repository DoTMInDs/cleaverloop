from django.urls import path
from apps.generations import views

app_name = 'generations'

urlpatterns = [
    path('', views.GenerationHistoryView.as_view(), name='history'),
    path('create/', views.create_generation_view, name='create'),
    path('<uuid:pk>/', views.GenerationDetailView.as_view(), name='detail'),
    path('<uuid:generation_id>/status/', views.generation_status_partial, name='status'),
    path('<uuid:generation_id>/favorite/', views.toggle_favorite_view, name='favorite'),
    path('<uuid:generation_id>/synthesize-audio/', views.synthesize_video_audio_view, name='synthesize_audio'),
    path('<uuid:generation_id>/lipsync/', views.lipsync_video_view, name='lipsync_video'),
    path('<uuid:generation_id>/mux-sound/', views.mux_audio_video_view, name='mux_audio_video'),
    path('api/generate-dialogue/', views.deduce_dialogue_api_view, name='api_generate_dialogue'),
]
