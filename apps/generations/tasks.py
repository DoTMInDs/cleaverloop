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

@shared_task(max_retries=3, default_retry_delay=5, time_limit=180, soft_time_limit=150)
def dispatch_generation_task(generation_id: str):

    """
    Asynchronously dispatch a generation job to the designated AI provider adapter.
    Handles immediate completion, async queueing, and automatic failure refunding.
    """
    try:
        generation = Generation.objects.select_related('user', 'provider', 'model', 'scene', 'project', 'character').get(id=generation_id)
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

        # If character is selected and no reference image was provided, attach character face anchor
        if not ref_urls and generation.character:
            candidate_urls = []
            if generation.character.face_anchor_url:
                candidate_urls.append(generation.character.face_anchor_url)
            if generation.character.primary_image_url:
                candidate_urls.append(generation.character.primary_image_url)
            if generation.character.avatar:
                try:
                    candidate_urls.append(generation.character.avatar.url)
                except Exception:
                    pass

            from apps.providers.base import load_image_as_base64
            for cand in candidate_urls:
                if cand:
                    try:
                        if load_image_as_base64(cand):
                            ref_urls.append(cand)
                            break
                    except Exception:
                        pass

        # Directorial character prompt injection — inject full visual DNA so the model generates the right person
        effective_prompt = generation.prompt
        if generation.character:
            char = generation.character
            # build_prompt_cue() assembles: gender, physique, appearance, clothing in one rich cue string
            char_cue = char.build_prompt_cue() if hasattr(char, 'build_prompt_cue') else ""
            if char.name.lower() not in effective_prompt.lower():
                if char_cue:
                    effective_prompt = f"{char_cue}. {effective_prompt}"
                else:
                    effective_prompt = f"{char.name}. {effective_prompt}"

        # Prevent headless/cropped bodies and guarantee photorealistic framing
        if generation.generation_type == 'video':
            framing_cues = (
                "cinematic medium close-up portrait shot, character's entire head and face clearly visible and centered, "
                "eye-level camera angle, eyes, nose, mouth and jawline fully in frame, "
                "photorealistic 4K hyper-detailed skin texture, natural cinematic lighting with soft rim light"
            )
            if not any(k in effective_prompt.lower() for k in ('portrait', 'headshot', 'medium close-up', 'close up', 'face centered', 'close-up')):
                effective_prompt = f"{effective_prompt}, {framing_cues}"

            # Anti-decapitation & anti-cropping negative prompt
            anti_crop = (
                "headless, cut off head, cropped head, head out of frame, missing head, decapitated, "
                "bad framing, top of head cut off, body without head, out of frame, "
                "distorted face, deformed features, bad anatomy, bad proportions, "
                "unnatural mouth, low quality, blurry, warped hands, ugly, poorly drawn"
            )
            if generation.negative_prompt:
                generation.negative_prompt = f"{generation.negative_prompt}, {anti_crop}"
            else:
                generation.negative_prompt = anti_crop

        extra_params = {}
        if generation.generation_type == 'audio':
            if generation.quality:
                extra_params['voice'] = generation.quality
            target_vp = generation.voice_profile
            if not target_vp and generation.character and generation.character.voice_profile:
                target_vp = generation.character.voice_profile
            if target_vp and target_vp.samples.exists():
                first_sample = target_vp.samples.first()
                if first_sample and first_sample.audio_file:
                    sample_path = first_sample.audio_file.path if hasattr(first_sample.audio_file, 'path') else first_sample.audio_file.url
                    extra_params['voice_sample_path'] = sample_path
                    extra_params['voice'] = str(target_vp.id)

        # -------------------------------------------------------------
        # 1-Step Unified Lip-Sync & Voice Route Routing
        # -------------------------------------------------------------
        is_google_veo = generation.provider.slug == 'google' or 'veo' in generation.model.model_id.lower()
        if generation.generation_type == 'video' and (generation.is_lip_sync or generation.voice_profile or generation.dialogue):
            dialogue_text = (generation.dialogue or "").strip()
            if not dialogue_text:
                # Auto-deduce realistic in-character spoken dialogue from the prompt
                try:
                    from apps.ai.dialogue import AIDialogueDirector
                    char_name = generation.character.name if generation.character else ""
                    char_gender = (generation.character.metadata.get('gender') or '') if generation.character else ""
                    deduced = AIDialogueDirector.deduce_dialogue(
                        prompt=generation.prompt,
                        character_name=char_name,
                        duration=generation.duration or 5,
                        character_gender=char_gender
                    )
                    dialogue_text = (deduced.get("dialogue") or "").strip()
                    if dialogue_text:
                        generation.dialogue = dialogue_text
                        generation.is_lip_sync = True
                        generation.save(update_fields=['dialogue', 'is_lip_sync'])
                        logger.info(f"Auto-deduced in-character dialogue for generation {generation.id}: '{dialogue_text}'")
                except Exception as exc:
                    logger.warning(f"Could not auto-deduce dialogue: {exc}")

            if is_google_veo and not generation.voice_profile:
                # ROUTE A: Google Veo Native Speech (ElevenLabs Bypassed)
                extra_params['dialogue'] = dialogue_text
                generation.uses_native_veo_audio = True
                generation.pipeline_stage = "Rendering cinematic video with Google Veo native speech..."
                generation.save(update_fields=['uses_native_veo_audio', 'pipeline_stage'])
            elif dialogue_text:
                # ROUTE B: Character Voice / Neural Lip-Sync Pipeline
                # Step 1: Pre-synthesize speech with character voice if not already attached
                if not generation.audio_track:
                    generation.pipeline_stage = "Stage 1/3: Synthesizing character speech in recorded voice..."
                    generation.save(update_fields=['pipeline_stage'])

                    # Resolve Voice Profile from generation or attached character
                    target_vp = generation.voice_profile
                    if not target_vp and generation.character and generation.character.voice_profile:
                        target_vp = generation.character.voice_profile
                        generation.voice_profile = target_vp
                        generation.save(update_fields=['voice_profile'])

                    audio_res = None

                    # CASE 1: Voice profile has user-recorded audio samples -> ZERO-SHOT NEURAL CLONE!
                    if target_vp and target_vp.samples.exists():
                        first_sample = target_vp.samples.first()
                        if first_sample and first_sample.audio_file:
                            sample_path = first_sample.audio_file.path if hasattr(first_sample.audio_file, 'path') else first_sample.audio_file.url
                            logger.info(f"Synthesizing character dialogue using authentic recorded voice sample '{target_vp.name}' via Fal F5-TTS")
                            from apps.providers.adapters.fal_ai import FalAIProvider
                            audio_res = FalAIProvider().clone_voice_speech(
                                text=dialogue_text,
                                ref_audio_path_or_url=sample_path
                            )

                    # CASE 2: Preset / remote voice or fallback
                    if not audio_res or audio_res.status != 'completed':
                        voice_target = 'adam'  # safe fallback
                        if target_vp:
                            pid = target_vp.provider_voice_id or ''
                            if pid and not pid.startswith('mock-') and not pid.startswith('fal-'):
                                voice_target = pid
                            else:
                                gender = (target_vp.gender or '').lower()
                                voice_target = 'rachel' if gender == 'female' else 'adam'
                        elif generation.quality and not generation.quality.startswith('mock-') and generation.quality not in ('standard', 'hd', 'hq'):
                            voice_target = generation.quality

                        from apps.providers.adapters.elevenlabs import ElevenLabsProvider
                        audio_req = GenerationRequest(
                            prompt=dialogue_text,
                            duration=generation.duration,
                            extra_params={'voice': voice_target}
                        )
                        audio_res = ElevenLabsProvider().generate_audio('eleven_multilingual_v2', audio_req)
                    if audio_res.status == 'completed' and audio_res.output_media_url:
                        audio_media = Media.objects.create(
                            owner=generation.user,
                            project=generation.project,
                            generation=generation,
                            media_type='audio',
                            storage_key=audio_res.output_media_url,
                            duration=generation.duration
                        )
                        # Download audio to local storage immediately for reliable mux access
                        import os
                        if audio_res.output_media_url.startswith(('http://', 'https://')):
                            from apps.providers.base import is_safe_external_url
                            if is_safe_external_url(audio_res.output_media_url):
                                try:
                                    audio_req_obj = urllib.request.Request(
                                        audio_res.output_media_url,
                                        headers={'User-Agent': 'CleaverLoop-Engine/1.0'}
                                    )
                                    with urllib.request.urlopen(audio_req_obj, timeout=20) as r:
                                        audio_bytes = r.read()
                                    if len(audio_bytes) > 512:
                                        ext = 'mp3' if audio_res.output_media_url.lower().endswith('.mp3') else 'wav'
                                        from django.core.files.base import ContentFile
                                        audio_media.file.save(f"{str(audio_media.id)[:8]}.{ext}", ContentFile(audio_bytes), save=True)
                                except Exception as dl_err:
                                    logger.warning(f"Could not pre-download audio for mux: {dl_err}")
                        generation.audio_track = audio_media
                        generation.save(update_fields=['audio_track'])
                        extra_params['audio_url'] = audio_media.url
                    else:
                        logger.warning(f"Speech synthesis failed for generation {generation.id}: {audio_res.error_message}")

                # Enhanced directorial framing prompt for natural jaw/lip motion
                effective_prompt = (
                    f"{effective_prompt}. Medium close-up portrait, natural conversational head motion, "
                    f"expressive jaw movement synchronized to speech, authentic eye contact, "
                    f"warm cinematic key light on face, shallow depth of field."
                )

        # For video lipsync/latentsync tasks, explicitly isolate video and audio reference assets
        if generation.generation_type == 'video' and any(k in generation.model.model_id.lower() for k in ('lipsync', 'latentsync')):
            video_ref = generation.reference_media.filter(media_type='video').first()
            if not video_ref and generation.parent_generation and generation.parent_generation.output_media:
                video_ref = generation.parent_generation.output_media

            audio_ref = generation.audio_track
            if not audio_ref:
                audio_ref = generation.reference_media.filter(media_type='audio').first()
            if not audio_ref and generation.parent_generation:
                audio_ref = generation.parent_generation.latest_audio

            if video_ref and video_ref.url:
                extra_params['video_url'] = video_ref.url
            if audio_ref and audio_ref.url:
                extra_params['audio_url'] = audio_ref.url

            # Ensure ref_urls has video first, audio second
            ordered_refs = []
            if video_ref and video_ref.url:
                ordered_refs.append(video_ref.url)
            if audio_ref and audio_ref.url:
                ordered_refs.append(audio_ref.url)
            for u in ref_urls:
                if u not in ordered_refs:
                    ordered_refs.append(u)
            ref_urls = ordered_refs

        req = GenerationRequest(
            prompt=effective_prompt,
            negative_prompt=generation.negative_prompt,
            aspect_ratio=generation.aspect_ratio,
            duration=generation.duration,
            quality=generation.quality,
            seed=generation.seed,
            reference_image_urls=ref_urls,
            correlation_id=str(generation.correlation_id),
            extra_params=extra_params,
        )

        # Call provider adapter based on type
        if generation.generation_type == 'image':
            result: ProviderJobResult = adapter.generate_image(generation.model.model_id, req)
        elif generation.generation_type == 'audio':
            result: ProviderJobResult = adapter.generate_audio(generation.model.model_id, req)
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
                elif generation.generation_type == 'audio':
                    fb_result = fallback_adapter.generate_audio(fallback_model.model_id, req)
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
        logger.error(f"Unhandled exception during generation {generation_id}: {exc}", exc_info=True)
        _finalize_failed_generation(generation, str(exc))

def check_and_update_generation_status(generation: Generation) -> Generation:
    """
    Check the upstream provider job status and finalize if complete or failed.
    Safe to call from HTMX polling views or background workers.
    """
    if generation.status in ('completed', 'failed', 'refunded', 'cancelled') or not generation.external_job_id:
        return generation

    try:
        adapter = ModelRegistry.get_provider_adapter(generation.provider.slug)
        result: ProviderJobResult = adapter.get_status(generation.external_job_id)

        if result.status == 'completed':
            _finalize_successful_generation(generation, result)
            generation.refresh_from_db()
        elif result.status == 'failed':
            logger.warning(f"Async generation job failed at provider: {result.error_message}")
            _finalize_failed_generation(generation, result.error_message or "Upstream generation job failed.")
            generation.refresh_from_db()
    except Exception as exc:
        logger.error(f"Error checking status for generation {generation.id}: {exc}")

    return generation

@shared_task(max_retries=None)
def poll_generation_task(generation_id: str, attempt: int = 1):

    """
    Periodic poller for asynchronous generation jobs.
    Evaluates provider status with backoff and finishes or fails over as needed.
    """
    try:
        generation = Generation.objects.get(id=generation_id)
        if generation.status in ('completed', 'failed', 'refunded', 'cancelled'):
            return

        check_and_update_generation_status(generation)
        generation.refresh_from_db()

        if generation.status in ('completed', 'failed', 'refunded', 'cancelled'):
            return

        # In eager development mode, avoid recursive blocking loops.
        # Browser HTMX polling will drive the live status checks.
        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
            return

        MAX_ATTEMPTS = 120  # ~8-10 minutes max wait for heavy video models (Wan 2.1 / Luma)
        if attempt >= MAX_ATTEMPTS:
            _finalize_failed_generation(generation, "Generation timed out waiting for provider response.")
            return

        # Re-schedule poller with adaptive backoff
        countdown = min(4 + (attempt // 10) * 2, 12)
        poll_generation_task.apply_async(args=[str(generation.id), attempt + 1], countdown=countdown)

    except Exception as exc:
        logger.error(f"Error polling generation {generation_id}: {exc}")
        MAX_ATTEMPTS = 120
        if attempt >= MAX_ATTEMPTS:
            _finalize_failed_generation(generation, f"Polling error: {str(exc)}")
        else:
            if not getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
                poll_generation_task.apply_async(args=[str(generation.id), attempt + 1], countdown=6)

def _finalize_successful_generation(generation: Generation, result: ProviderJobResult):
    """Create Media asset, link to generation/scene/project, commit credits, and mark complete."""
    with transaction.atomic():
        if generation.generation_type == 'image':
            media_type = 'image'
            ext = 'png' if result.output_media_url and '.png' in result.output_media_url.lower() else 'jpg'
        elif generation.generation_type == 'audio':
            media_type = 'audio'
            if result.output_media_url and '.mp3' in result.output_media_url.lower():
                ext = 'mp3'
            elif result.output_media_url and '.ogg' in result.output_media_url.lower():
                ext = 'ogg'
            else:
                ext = 'wav'
        else:
            media_type = 'video'
            ext = 'mp4'
        
        media = Media.objects.create(
            owner=generation.user,
            project=generation.project,
            generation=generation,
            media_type=media_type,
            width=generation.width if media_type != 'audio' else None,
            height=generation.height if media_type != 'audio' else None,
            duration=generation.duration if media_type in ('video', 'audio') else None,
            storage_key=result.output_media_url or "",
        )

        # Download remote output URL if external HTTP URL (enforcing SSRF and 50MB streaming safety limit)
        MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
        if result.output_media_url and result.output_media_url.startswith(('http://', 'https://')):
            if is_safe_external_url(result.output_media_url):
                try:
                    req = urllib.request.Request(result.output_media_url, headers={'User-Agent': 'CleaverLoop-Engine/1.0'})
                    with urllib.request.urlopen(req, timeout=30) as resp:
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

        # Automatic Audio Muxing: If this completed video has an audio_track attached, immediately mux it into the MP4 container!
        if generation.generation_type == 'video' and generation.audio_track and media.file:
            try:
                import os
                from apps.editor.ffmpeg_service import FFmpegService
                if os.path.exists(media.file.path) and generation.audio_track.file and os.path.exists(generation.audio_track.file.path):
                    muxed_path = FFmpegService.merge_video_and_audio(media.file.path, generation.audio_track.file.path)
                    if muxed_path and os.path.exists(muxed_path) and muxed_path != media.file.path:
                        with open(muxed_path, 'rb') as f:
                            media.file.save(f"{str(media.id)[:8]}_voiced.mp4", ContentFile(f.read()), save=True)
                        logger.info(f"Automatically muxed character voice audio track into base video {generation.id}")
            except Exception as mux_err:
                logger.warning(f"Auto audio mux on base video completion failed: {mux_err}")

        generation.output_media = media
        generation.status = 'completed'
        generation.completed_at = timezone.now()
        generation.save(update_fields=['output_media', 'status', 'completed_at', 'external_job_id', 'model', 'provider', 'model_id_snapshot', 'admin_error_detail'])

        # If attached to a project scene, link it
        if generation.scene:
            if generation.generation_type != 'audio' or not generation.scene.generated_media:
                generation.scene.generated_media = media
            generation.scene.status = 'completed'
            generation.scene.save(update_fields=['generated_media', 'status'])

        # If attached to a parent video generation:
        if generation.parent_generation:
            # Case A: Audio track generation completed -> link audio_track & auto-mux sound
            if generation.generation_type == 'audio':
                generation.parent_generation.audio_track = media
                generation.parent_generation.save(update_fields=['audio_track'])
                try:
                    import os
                    from apps.editor.ffmpeg_service import FFmpegService
                    parent_med = generation.parent_generation.output_media
                    if parent_med and parent_med.file and media.file:
                        if os.path.exists(parent_med.file.path) and os.path.exists(media.file.path):
                            muxed_path = FFmpegService.merge_video_and_audio(parent_med.file.path, media.file.path)
                            if muxed_path and os.path.exists(muxed_path) and muxed_path != parent_med.file.path:
                                with open(muxed_path, 'rb') as f:
                                    parent_med.file.save(f"{parent_med.id}_voiced.mp4", ContentFile(f.read()), save=True)
                                logger.info(f"Automatically muxed audio track into parent video {parent_med.id}")
                except Exception as e:
                    logger.warning(f"Auto audio-video mux failed: {e}")

                # Automatically trigger neural lip-sync if attached to base video
                if generation.parent_generation.output_media and not any(k in generation.parent_generation.model.model_id.lower() for k in ('lipsync', 'latentsync')):
                    _trigger_unified_neural_lipsync(generation.parent_generation)

            # Case B: Child Video (e.g. Neural Lip-Sync pass) completed -> promote to parent video output!
            elif generation.generation_type == 'video':
                generation.parent_generation.output_media = media
                generation.parent_generation.pipeline_stage = "Neural lip-sync and audio integration complete!"
                generation.parent_generation.save(update_fields=['output_media', 'pipeline_stage'])
                logger.info(f"Promoted lip-synced video media {media.id} to parent generation {generation.parent_generation.id}")

        # If this is a 1-step lip-sync generation that just finished base video, trigger neural lip-sync step!
        if generation.generation_type == 'video' and generation.is_lip_sync and generation.audio_track and not any(k in generation.model.model_id.lower() for k in ('lipsync', 'latentsync')):
            _trigger_unified_neural_lipsync(generation)

        # Commit credits
        CreditService.commit_credits(generation)
        logger.info(f"Successfully finalized generation {generation.id}")

def _trigger_unified_neural_lipsync(parent_gen: Generation):
    """
    1-Step Unified Lip-Sync Pipeline: Automatically launches neural lip-sync pass
    after base video finishes, connecting the base video with the cloned audio track.
    """
    try:
        from apps.providers.models import AIModel, AIProviderConfig
        fal_cfg = AIProviderConfig.objects.filter(slug='fal').first() or parent_gen.provider
        lipsync_model = AIModel.objects.filter(model_id='fal-latentsync', is_enabled=True).first()
        if not lipsync_model:
            lipsync_model, _ = AIModel.objects.get_or_create(
                model_id='fal-latentsync',
                defaults={
                    'provider': fal_cfg,
                    'display_name': 'LatentSync (Full-Face & Jaw Neural)',
                    'modality': 'video',
                    'credit_cost_fixed': 15,
                    'credit_cost_per_second': 3,
                    'is_enabled': True
                }
            )

        duration = parent_gen.duration or 5
        parent_gen.pipeline_stage = "Stage 3/3: Running full-face neural lip-sync & jaw articulation..."
        parent_gen.save(update_fields=['pipeline_stage'])

        lipsync_gen = Generation.objects.create(
            user=parent_gen.user,
            project=parent_gen.project,
            parent_generation=parent_gen,
            generation_type='video',
            provider=lipsync_model.provider,
            model=lipsync_model,
            model_id_snapshot=lipsync_model.model_id,
            prompt=f"👄 Neural Lip-Sync: {parent_gen.prompt}",
            aspect_ratio=parent_gen.aspect_ratio,
            duration=duration,
            character=parent_gen.character,
            audio_track=parent_gen.audio_track,
            status='queued'
        )
        if parent_gen.output_media:
            lipsync_gen.reference_media.add(parent_gen.output_media)
        if parent_gen.audio_track:
            lipsync_gen.reference_media.add(parent_gen.audio_track)

        dispatch_generation_task.delay(str(lipsync_gen.id))
        logger.info(f"Triggered automated unified lip-sync job {lipsync_gen.id} for parent {parent_gen.id}")
    except Exception as exc:
        logger.error(f"Could not trigger automated neural lip-sync for {parent_gen.id}: {exc}")

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


def reap_stale_generations(user=None, timeout_minutes: int = 15):
    """
    Identifies stuck generations older than timeout_minutes, marks them as failed,
    and automatically refunds any held credits to the user.
    """
    cutoff = timezone.now() - timezone.timedelta(minutes=timeout_minutes)
    qs = Generation.objects.filter(
        status__in=['queued', 'processing'],
        created_at__lte=cutoff
    ).select_related('user', 'provider', 'model', 'scene')
    
    if user and user.is_authenticated:
        qs = qs.filter(user=user)

    reaped_count = 0
    for gen in qs:
        try:
            logger.warning(f"Reaping stale generation {gen.id} (created at {gen.created_at})")
            _finalize_failed_generation(gen, f"Generation timed out after {timeout_minutes} minutes without completion.")
            reaped_count += 1
        except Exception as e:
            logger.warning(f"Could not reap stale generation {gen.id}: {e}")

    if reaped_count > 0:
        logger.info(f"Stale generation reaper finished: {reaped_count} jobs cleaned and refunded.")
    return reaped_count


@shared_task
def reap_stale_generations_task(timeout_minutes: int = 15):
    """
    Scheduled / worker maintenance task: Identifies stuck generations older than timeout_minutes,
    marks them as timed out/failed, and automatically refunds any held credits to the user.
    """
    return reap_stale_generations(timeout_minutes=timeout_minutes)


