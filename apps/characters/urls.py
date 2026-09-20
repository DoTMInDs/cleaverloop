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
]
