import logging
import urllib.request
import io
from celery import shared_task
from django.utils import timezone
from django.core.files.base import ContentFile
from django.db import transaction

from apps.generations.models import Generation
from apps.media.models import Media
from apps.credits.services import CreditService
from apps.providers.registry import ModelRegistry
from apps.providers.base import GenerationRequest, ProviderJobResult

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def dispatch_generation_task(self, generation_id: str):
    """
    Asynchronously dispatch a generation job to the designated AI provider adapter.
    Handles immediate completion, async queueing, and automatic failure refunding.
    """
    try:
        generation = Generation.objects.select_related('user', 'provider', 'model', 'scene', 'project').get(id=generation_id)
    except Generation.DoesNotExist:
        logger.error(f"Generation with ID {generation_id} not found.")
        return

    generation.started_at = timezone.now()
    generation.status = 'processing'
    generation.save(update_fields=['status', 'started_at'])

    try:
        adapter = ModelRegistry.get_provider_adapter(generation.provider.slug)
        
        # Collect reference media URLs if any
        ref_urls = [m.url for m in generation.reference_media.all() if m.url]

        req = GenerationRequest(
            prompt=generation.prompt,
            negative_prompt=generation.negative_prompt,
            aspect_ratio=generation.aspect_ratio,
            duration=generation.duration,
            quality=generation.quality,
            seed=generation.seed,
            reference_image_urls=ref_urls,
            correlation_id=str(generation.correlation_id),
        )

        # Call provider adapter based on type
        if generation.generation_type == 'image':
            result: ProviderJobResult = adapter.generate_image(generation.model.model_id, req)
        else:
            result: ProviderJobResult = adapter.generate_video(generation.model.model_id, req)

        generation.external_job_id = result.external_job_id
        generation.provider_response = result.raw_response

        if result.status == 'completed':
            _finalize_successful_generation(generation, result)
        elif result.status in ('queued', 'processing'):
            generation.save(update_fields=['external_job_id', 'provider_response', 'status'])
            # Schedule poller task
            poll_generation_task.apply_async(
                args=[str(generation.id), 1],
                countdown=3
            )
        else:
            # Immediate provider failure
            _finalize_failed_generation(generation, result.error_message or "Upstream generation failure")

    except Exception as exc:
        logger.exception(f"Unhandled exception during generation {generation_id}: {exc}")
        _finalize_failed_generation(generation, str(exc))

@shared_task(bind=True)
def poll_generation_task(self, generation_id: str, attempt: int = 1):
    """Poll upstream provider for async video/image task completion."""
    try:
        generation = Generation.objects.select_related('user', 'provider', 'model', 'scene', 'project').get(id=generation_id)
    except Generation.DoesNotExist:
        return

    if generation.status in ('completed', 'failed', 'refunded', 'cancelled'):
        return

    MAX_ATTEMPTS = 40  # Max ~3 minutes polling

    try:
        adapter = ModelRegistry.get_provider_adapter(generation.provider.slug)
        result = adapter.get_status(generation.external_job_id)

        if result.status == 'completed':
            _finalize_successful_generation(generation, result)
        elif result.status == 'failed':
            _finalize_failed_generation(generation, result.error_message or "Generation failed upstream")
        else:
            if attempt >= MAX_ATTEMPTS:
                _finalize_failed_generation(generation, "Generation timed out waiting for provider response.")
            else:
                # Re-queue next poll attempt with 4-second backoff
                poll_generation_task.apply_async(
                    args=[str(generation.id), attempt + 1],
                    countdown=4
                )
    except Exception as exc:
        logger.error(f"Error polling generation {generation_id}: {exc}")
        if attempt >= MAX_ATTEMPTS:
            _finalize_failed_generation(generation, f"Polling error: {str(exc)}")
        else:
            poll_generation_task.apply_async(args=[str(generation.id), attempt + 1], countdown=5)

def _finalize_successful_generation(generation: Generation, result: ProviderJobResult):
    """Create Media asset, link to generation/scene/project, commit credits, and mark complete."""
    with transaction.atomic():
        media_type = 'image' if generation.generation_type == 'image' else 'video'
        
        media = Media.objects.create(
            owner=generation.user,
            project=generation.project,
            generation=generation,
            media_type=media_type,
            width=generation.width,
            height=generation.height,
            duration=generation.duration if media_type == 'video' else None,
            storage_key=result.output_media_url or "",
        )

        # Download remote output URL if external HTTP URL
        if result.output_media_url and result.output_media_url.startswith(('http://', 'https://')):
            try:
                req = urllib.request.Request(result.output_media_url, headers={'User-Agent': 'CleverLoop-Engine/1.0'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    ext = "mp4" if media_type == 'video' else "jpg"
                    content = resp.read()
                    media.file.save(f"{media.id}.{ext}", ContentFile(content), save=False)
                    media.file_size = len(content)
            except Exception as e:
                logger.warning(f"Could not download remote file into local storage: {e}")

        media.save()

        generation.output_media = media
        generation.status = 'completed'
        generation.completed_at = timezone.now()
        generation.save(update_fields=['output_media', 'status', 'completed_at', 'external_job_id'])

        # If attached to a project scene, link it
        if generation.scene:
            generation.scene.generated_media = media
            generation.scene.status = 'completed'
            generation.scene.save(update_fields=['generated_media', 'status'])

        # Commit credits
        CreditService.commit_credits(generation)
        logger.info(f"Successfully finalized generation {generation.id}")

def _finalize_failed_generation(generation: Generation, raw_error: str):
    """Mark generation as failed, record diagnostics, and automatically refund reserved credits."""
    with transaction.atomic():
        generation.status = 'failed'
        generation.admin_error_detail = raw_error
        generation.error_message = (
            f"Generation could not be completed by {generation.provider.name}. "
            f"Your {generation.credits_reserved} credits have been restored to your wallet."
        )
        generation.completed_at = timezone.now()
        generation.save(update_fields=['status', 'admin_error_detail', 'error_message', 'completed_at'])

        if generation.scene:
            generation.scene.status = 'failed'
            generation.scene.save(update_fields=['status'])

        # Refund credits back to wallet
        CreditService.refund_credits(generation, reason=f"Generation failed: {raw_error[:100]}")
        logger.warning(f"Generation {generation.id} failed. Credits refunded.")
