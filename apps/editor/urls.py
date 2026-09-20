from django.urls import path
from apps.editor import views

app_name = 'editor'

urlpatterns = [
    path('jobs/<uuid:job_id>/status/', views.job_status_api, name='job_status'),
]
