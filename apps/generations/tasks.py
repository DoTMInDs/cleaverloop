import logging
import urllib.request
import io
from celery import shared_task
from django.utils import timezone
from django.core.files.base import ContentFile
from django.db import transaction
from django.conf import settings

from apps.generations.models import Generation
from apps.media.models import Media
from apps.credits.services import CreditService
from apps.providers.registry import ModelRegistry
from apps.providers.base import GenerationRequest, ProviderJobResult, is_safe_external_url

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=5, time_limit=180, soft_time_limit=150)
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
            # Immediate provider failure (e.g. 429 Quota or 1008 Balance)
            logger.warning(
                f"Primary model {generation.model_id_snapshot} failed ({result.error_message}). "
                f"Attempting dynamic failover to alternative provider."
            )
            from apps.providers.router import ModelRouter

            primary_name = generation.model.display_name
            primary_id = generation.model.model_id
            primary_err = result.error_message or "Upstream generation failure"
            chain_logs = [f"{primary_name} ({primary_id}): {primary_err}"]

            attempted_slugs = [generation.provider.slug]
            current_model = generation.model

            # Classify primary error into a friendly concise reason
            simple_reason = "upstream rate limit or quota reached"
            if "429" in primary_err or "quota" in primary_err.lower() or "exhausted" in primary_err.lower():
                simple_reason = "quota / rate limit reached"
            elif "balance" in primary_err.lower() or "403" in primary_err or "1102" in primary_err or "1008" in primary_err:
                simple_reason = "balance exhausted"
            elif "404" in primary_err:
                simple_reason = "model endpoint unavailable on API key"

            # Try fallback tiers: live alternatives (Fal.ai, MiniMax, Kling), then mock safety net
            max_attempts = 6 if getattr(settings, 'MOCK_PROVIDERS_ENABLED', True) else 3
            for _ in range(max_attempts):
                fallback_model = ModelRouter.get_fallback_model(
                    failed_model=current_model,
                    duration=generation.duration,
                    has_refs=bool(ref_urls),
                    excluded_provider_slugs=attempted_slugs
                )
                if not fallback_model or fallback_model.id == current_model.id:
                    break

                attempted_slugs.append(fallback_model.provider.slug)
                current_model = fallback_model
                logger.info(f"Failing over generation {generation.id} to [{fallback_model.model_id}] ({fallback_model.provider.name})")

                fallback_adapter = ModelRegistry.get_provider_adapter(fallback_model.provider.slug)
                if generation.generation_type == 'image':
                    fb_result = fallback_adapter.generate_image(fallback_model.model_id, req)
                else:
                    fb_result = fallback_adapter.generate_video(fallback_model.model_id, req)

                if fb_result.status in ('completed', 'queued', 'processing'):
                    generation.model = fallback_model
                    generation.provider = fallback_model.provider
                    generation.model_id_snapshot = fallback_model.model_id
                    generation.admin_error_detail = (
                        f"Generated via {fallback_model.display_name} "
                        f"(automatic failover from {primary_name} due to {simple_reason})."
                    )
                    generation.external_job_id = fb_result.external_job_id
                    generation.provider_response = fb_result.raw_response

                    if fb_result.status == 'completed':
                        _finalize_successful_generation(generation, fb_result)
                    else:
                        generation.save(update_fields=['model', 'provider', 'model_id_snapshot', 'admin_error_detail', 'external_job_id', 'provider_response', 'status'])
                        poll_generation_task.apply_async(args=[str(generation.id), 1], countdown=3)
                    return
                else:
                    chain_logs.append(f"{fallback_model.display_name} ({fallback_model.model_id}): {fb_result.error_message}")

            # If all fallback attempts failed or no eligible fallback found
            combined_err = " -> ".join(chain_logs)
            _finalize_failed_generation(generation, combined_err)

    except Exception as exc:
        logger.exception(f"Unhandled exception during generation {generation_id}: {exc}")
        _finalize_failed_generation(generation, str(exc))

@shared_task(bind=True, time_limit=120, soft_time_limit=90)
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
                if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
                    import time
                    time.sleep(4)
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
            if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
                import time
                time.sleep(4)
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

        # Download remote output URL if external HTTP URL (enforcing SSRF and 50MB streaming safety limit)
        MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
        if result.output_media_url and result.output_media_url.startswith(('http://', 'https://')):
            if is_safe_external_url(result.output_media_url):
                try:
                    req = urllib.request.Request(result.output_media_url, headers={'User-Agent': 'CleaverLoop-Engine/1.0'})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        ext = "mp4" if media_type == 'video' else "jpg"
                        chunks = []
                        total_bytes = 0
                        while True:
                            chunk = resp.read(65536)  # 64KB chunks
                            if not chunk:
                                break
                            total_bytes += len(chunk)
                            if total_bytes > MAX_DOWNLOAD_BYTES:
                                logger.warning(f"Remote file exceeded {MAX_DOWNLOAD_BYTES} bytes. Truncating download.")
                                break
                            chunks.append(chunk)

                        content = b"".join(chunks)
                        if len(content) >= 512:
                            media.file.save(f"{media.id}.{ext}", ContentFile(content), save=False)
                            media.file_size = len(content)
                        else:
                            logger.warning(f"Downloaded media too small ({len(content)} bytes), likely corrupted.")
                except Exception as e:
                    logger.warning(f"Could not download remote file into local storage: {e}")
            else:
                logger.warning(f"Blocked downloading from unsafe or non-public URL: {result.output_media_url}")

        media.save()

        generation.output_media = media
        generation.status = 'completed'
        generation.completed_at = timezone.now()
        generation.save(update_fields=['output_media', 'status', 'completed_at', 'external_job_id', 'model', 'provider', 'model_id_snapshot', 'admin_error_detail'])

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
        logger.error(
            f"\n"
            f"================================================================================\n"
            f"[GENERATION FAILED DIAGNOSTICS]\n"
            f"Generation ID : {generation.id}\n"
            f"Provider      : {generation.provider.name} ({generation.provider.slug})\n"
            f"Model         : {generation.model_id_snapshot}\n"
            f"Prompt        : {generation.prompt[:80]}...\n"
            f"Error Detail  : {raw_error}\n"
            f"Action Taken  : {generation.credits_reserved} credits automatically refunded\n"
            f"================================================================================"
        )


@shared_task
def reap_stale_generations_task(timeout_minutes: int = 15):
    """
    Scheduled / worker maintenance task: Identifies stuck generations older than timeout_minutes,
    marks them as timed out/failed, and automatically refunds any held credits to the user.
    """
    cutoff = timezone.now() - timezone.timedelta(minutes=timeout_minutes)
    stale_generations = Generation.objects.filter(
        status__in=['queued', 'processing'],
        created_at__lte=cutoff
    ).select_related('user', 'provider', 'model', 'scene')

    reaped_count = 0
    for gen in stale_generations:
        logger.warning(f"Reaping stale generation {gen.id} (created at {gen.created_at})")
        _finalize_failed_generation(gen, f"Generation timed out after {timeout_minutes} minutes without completion.")
        reaped_count += 1

    logger.info(f"Stale generation reaper finished: {reaped_count} jobs cleaned and refunded.")
    return reaped_count

