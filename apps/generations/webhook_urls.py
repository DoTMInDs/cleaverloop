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

    import os
    import hmac
    from apps.providers.models import AIProviderConfig

    provider = AIProviderConfig.objects.filter(slug=provider_slug, is_enabled=True).first()
    if not provider:
        logger.warning(f"Webhook received for unknown or disabled provider: {provider_slug}")
        return HttpResponse("Provider not recognized", status=404)

    # If webhook secret is configured for this provider, verify signature or token
    if provider.webhook_secret_env_var:
        secret = os.environ.get(provider.webhook_secret_env_var, '')
        if secret:
            token = request.headers.get('X-Webhook-Secret') or request.headers.get('Authorization', '').replace('Bearer ', '').strip() or request.GET.get('token')
            if not token or not hmac.compare_digest(token, secret):
                logger.warning(f"Unauthorized webhook attempt for provider: {provider_slug}")
                return HttpResponse("Unauthorized webhook signature", status=401)

    external_job_id = payload.get("id") or payload.get("task_id") or payload.get("name")
    if not external_job_id:
        return HttpResponse("Missing external task identifier", status=400)

    generation = Generation.objects.filter(external_job_id=external_job_id, provider=provider).first()
    if not generation:
        logger.warning(f"Webhook received for unknown external job: {external_job_id} on provider {provider_slug}")
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
