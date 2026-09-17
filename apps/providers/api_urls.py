from django.http import JsonResponse
from django.urls import path
from apps.providers.models import AIModel

def list_models_api(request):
    modality = request.GET.get('modality')
    qs = AIModel.objects.filter(is_enabled=True, provider__is_enabled=True)
    if modality:
        qs = qs.filter(modality=modality)
    data = [{
        "model_id": m.model_id,
        "display_name": m.display_name,
        "provider": m.provider.name,
        "modality": m.modality,
        "credit_cost_fixed": m.credit_cost_fixed,
        "credit_cost_per_second": m.credit_cost_per_second,
        "aspect_ratios": m.supported_aspect_ratios,
        "supports_image_reference": m.supports_image_reference,
    } for m in qs]
    return JsonResponse({"models": data})

urlpatterns = [
    path('models/', list_models_api, name='api-models-list'),
]
