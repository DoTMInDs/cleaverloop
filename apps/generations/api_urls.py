from django.http import JsonResponse
from django.urls import path
from apps.generations.models import Generation

def list_generations_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    gens = Generation.objects.filter(user=request.user)[:20]
    data = [{
        "id": str(g.id),
        "type": g.generation_type,
        "status": g.status,
        "prompt": g.prompt,
        "media_url": g.output_media.url if g.output_media else "",
        "created_at": g.created_at.isoformat()
    } for g in gens]
    return JsonResponse({"generations": data})

urlpatterns = [
    path('', list_generations_api, name='api-generations-list'),
]
