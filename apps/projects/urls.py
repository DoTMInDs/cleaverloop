from django.urls import path
from apps.projects import views

app_name = 'projects'

urlpatterns = [
    path('', views.ProjectListView.as_view(), name='list'),
    path('new/', views.ProjectCreateView.as_view(), name='create'),
    path('<uuid:pk>/', views.ProjectDetailView.as_view(), name='detail'),
    path('scenes/<uuid:scene_id>/generate/', views.generate_scene_view, name='generate_scene'),
    path('<uuid:project_id>/assemble/', views.assemble_project_view, name='assemble'),
]
