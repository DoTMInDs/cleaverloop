from django.http import JsonResponse
from django.urls import path
from apps.characters.models import Character

def list_characters_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    chars = Character.objects.filter(owner=request.user)
    data = [{
        "id": str(c.id),
        "name": c.name,
        "avatar_url": c.avatar.url if c.avatar else "",
        "appearance": c.appearance_description
    } for c in chars]
    return JsonResponse({"characters": data})

urlpatterns = [
    path('', list_characters_api, name='api-characters-list'),
]
