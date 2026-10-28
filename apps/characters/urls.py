from django.urls import path
from apps.characters import views

app_name = 'characters'

urlpatterns = [
    path('', views.CharacterListView.as_view(), name='list'),
    path('new/', views.CharacterCreateView.as_view(), name='create'),
    path('generate-ai/', views.generate_character_ai_view, name='generate_ai'),
    path('<uuid:pk>/', views.CharacterDetailView.as_view(), name='detail'),
    path('<uuid:pk>/edit/', views.CharacterUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/delete/', views.CharacterDeleteView.as_view(), name='delete'),
    path('<uuid:pk>/poses/set-primary/', views.set_primary_pose_view, name='set_primary_pose'),
    path('<uuid:pk>/variant/', views.create_character_variant_view, name='create_variant'),
    path('<uuid:pk>/turnaround/', views.generate_turnaround_sheet_view, name='generate_turnaround'),
    path('assets/create/', views.create_scene_asset_view, name='create_asset'),
    path('assets/<uuid:asset_id>/delete/', views.delete_scene_asset_view, name='delete_asset'),
]
