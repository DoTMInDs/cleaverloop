from django.urls import path
from apps.characters import views

app_name = 'characters'

urlpatterns = [
    path('', views.CharacterListView.as_view(), name='list'),
    path('new/', views.CharacterCreateView.as_view(), name='create'),
    path('<uuid:pk>/', views.CharacterDetailView.as_view(), name='detail'),
]
