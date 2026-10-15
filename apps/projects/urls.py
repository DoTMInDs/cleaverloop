from django.urls import path
from apps.projects import views

app_name = 'projects'

urlpatterns = [
    path('', views.ProjectListView.as_view(), name='list'),
    path('new/', views.ProjectCreateView.as_view(), name='create'),
    path('<uuid:pk>/', views.ProjectDetailView.as_view(), name='detail'),
    path('<uuid:pk>/delete/', views.ProjectDeleteView.as_view(), name='delete'),
    path('<uuid:project_id>/scenes/add/', views.add_scene_view, name='add_scene'),
    path('<uuid:project_id>/scenes/batch-upload/', views.batch_upload_scenes_view, name='batch_upload_scenes'),
    path('scenes/<uuid:scene_id>/delete/', views.delete_scene_view, name='delete_scene'),
    path('scenes/<uuid:scene_id>/generate/', views.generate_scene_view, name='generate_scene'),
    path('scenes/<uuid:scene_id>/audio/', views.generate_scene_audio_view, name='generate_scene_audio'),
    path('scenes/<uuid:scene_id>/status/', views.scene_status_view, name='scene_status'),
    path('scenes/<uuid:scene_id>/upload/', views.upload_scene_video_view, name='upload_scene_video'),
    path('scenes/<uuid:scene_id>/reorder/<str:direction>/', views.reorder_scene_view, name='reorder_scene'),
    path('<uuid:project_id>/assemble/', views.assemble_project_view, name='assemble'),
]

