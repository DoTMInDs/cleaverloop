from django.urls import path
from apps.generations import views

app_name = 'generations'

urlpatterns = [
    path('', views.GenerationHistoryView.as_view(), name='history'),
    path('create/', views.create_generation_view, name='create'),
    path('<uuid:pk>/', views.GenerationDetailView.as_view(), name='detail'),
    path('<uuid:generation_id>/status/', views.generation_status_partial, name='status'),
    path('<uuid:generation_id>/favorite/', views.toggle_favorite_view, name='favorite'),
]
