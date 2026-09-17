import json
import logging
from django.http import JsonResponse, HttpResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.generations.models import Generation
from apps.generations.tasks import _finalize_successful_generation, _finalize_failed_generation
from apps.providers.base import ProviderJobResult

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def universal_provider_webhook(request, provider_slug):
    """
    Idempotent webhook receiver for AI providers (Google, Kling, ByteDance, etc.).
    Processes external completion callbacks and settles credits.
    """
    try:
        payload = json.loads(request.body)
    except Exception:
        return HttpResponse("Invalid JSON", status=400)

    external_job_id = payload.get("id") or payload.get("task_id") or payload.get("name")
    if not external_job_id:
        return HttpResponse("Missing external task identifier", status=400)

    generation = Generation.objects.filter(external_job_id=external_job_id).first()
    if not generation:
        logger.warning(f"Webhook received for unknown external job: {external_job_id}")
        return JsonResponse({"status": "ignored", "reason": "job not found"}, status=200)

    if generation.status in ('completed', 'failed', 'refunded'):
        return JsonResponse({"status": "already_processed"}, status=200)

    # Determine status from payload
    status_str = str(payload.get("status", "")).lower()
    if status_str in ("completed", "succeed", "success", "done"):
        output_url = payload.get("output_url") or payload.get("video_url") or payload.get("image_url")
        result = ProviderJobResult(
            external_job_id=external_job_id,
            status="completed",
            output_media_url=output_url,
            raw_response=payload
        )
        _finalize_successful_generation(generation, result)
    elif status_str in ("failed", "error"):
        error_msg = payload.get("error_message") or payload.get("error") or "Webhook reported generation failed"
        _finalize_failed_generation(generation, error_msg)

    return JsonResponse({"status": "processed"})

urlpatterns = [
    path('<str:provider_slug>/', universal_provider_webhook, name='webhook'),
]
