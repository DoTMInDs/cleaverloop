from django.http import JsonResponse
from django.urls import path
from apps.projects.models import Project

def list_projects_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    projects = Project.objects.filter(owner=request.user)
    data = [{
        "id": str(p.id),
        "name": p.name,
        "aspect_ratio": p.aspect_ratio,
        "status": p.status,
        "scenes_count": p.scenes.count()
    } for p in projects]
    return JsonResponse({"projects": data})

urlpatterns = [
    path('', list_projects_api, name='api-projects-list'),
]
