import logging
import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView

logger = logging.getLogger(__name__)

from apps.characters.models import Character
from apps.credits.services import CreditService
from apps.generations.models import Generation
from apps.generations.tasks import dispatch_generation_task, reap_stale_generations
from apps.media.models import Media
from apps.providers.models import AIModel
from apps.providers.router import ModelRouter

ALLOWED_REF_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'mp4', 'mov'}
MAX_REF_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

class GenerationHistoryView(LoginRequiredMixin, ListView):
    model = Generation
    template_name = 'studio/history.html'
    context_object_name = 'generations'
    paginate_by = 24

    def get_queryset(self):
        reap_stale_generations(user=self.request.user, timeout_minutes=15)
        qs = Generation.objects.filter(user=self.request.user, parent_generation__isnull=True).select_related('output_media', 'model', 'provider')
        filter_type = self.request.GET.get('type')
        if filter_type in ('image', 'video'):
            qs = qs.filter(generation_type=filter_type)
        elif filter_type == 'audio':
            qs = Generation.objects.filter(user=self.request.user, generation_type='audio').select_related('output_media', 'model', 'provider')
        elif filter_type == 'failed':
            qs = qs.filter(status='failed')
        elif filter_type == 'favorites':
            qs = qs.filter(is_favorite=True)
        return qs

class GenerationDetailView(LoginRequiredMixin, DetailView):
    model = Generation
    template_name = 'studio/generation_detail.html'
    context_object_name = 'generation'

    def get_queryset(self):
        return Generation.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.providers.adapters.elevenlabs import ElevenLabsProvider
        from apps.generations.tasks import check_and_update_generation_status, dispatch_generation_task

        # If this generation is currently queued or processing, refresh provider status
        if self.object.status in ['queued', 'processing']:
            try:
                if self.object.status == 'queued' and not self.object.external_job_id:
                    dispatch_generation_task(str(self.object.id))
                else:
                    self.object = check_and_update_generation_status(self.object)
            except Exception as e:
                logger.warning(f"Error updating generation {self.object.id} status: {e}")
            self.object.refresh_from_db()

        # Process any pending child audio synthesis jobs
        if self.object.is_synthesizing_audio:
            for child in self.object.child_generations.filter(generation_type='audio', status__in=['queued', 'processing']):
                try:
                    if child.status == 'queued':
                        dispatch_generation_task(str(child.id))
                    else:
                        check_and_update_generation_status(child)
                except Exception as e:
                    logger.warning(f"Error checking child audio generation {child.id}: {e}")
            self.object.refresh_from_db()

        ctx['available_voices'] = ElevenLabsProvider.get_available_voices()
        duration = self.object.duration or 5
        audio_model = AIModel.objects.filter(modality='audio', is_enabled=True).order_by('-priority').first()
        ctx['audio_credit_cost'] = audio_model.calculate_credit_cost(duration=duration) if audio_model else 25
        return ctx


def _get_generation_partial_context(generation: Generation) -> dict:
    from apps.providers.adapters.elevenlabs import ElevenLabsProvider
    duration = generation.duration or 5
    audio_model = AIModel.objects.filter(modality='audio', is_enabled=True).order_by('-priority').first()
    credit_cost = audio_model.calculate_credit_cost(duration=duration) if audio_model else 25
    return {
        'generation': generation,
        'available_voices': ElevenLabsProvider.get_available_voices(),
        'audio_credit_cost': credit_cost,
    }

def _render_error_card(message: str, is_credit_error: bool = False, is_staff_or_debug: bool = False) -> str:
    action_html = ""
    if is_credit_error:
        refill_button = ""
        if is_staff_or_debug:
            refill_button = """
                <form action="/credits/quick-refill/" method="POST" class="inline" hx-post="/credits/quick-refill/" hx-target="#active-generation-target" hx-swap="innerHTML">
                    <button type="submit" class="btn btn-xs btn-primary bg-gradient-to-r from-brand-600 to-indigo-600 text-white border-none text-[10px]">
                        ⚡ Free Dev Refill (+1,000 Credits)
                    </button>
                </form>
            """
        action_html = f"""
        <div class="mt-3 pt-3 border-t border-rose-500/20 flex flex-wrap items-center justify-between gap-2">
            <span class="text-[11px] text-rose-300">Need more credits to continue creating?</span>
            <div class="flex items-center gap-2">
                <a href="/billing/plans/" class="btn btn-xs btn-primary bg-brand-600 hover:bg-brand-500 text-white border-none text-[10px]">Upgrade Plan</a>
                <a href="/credits/wallet/" class="btn btn-xs btn-outline btn-error text-[10px]">View Wallet</a>
                {refill_button}
            </div>
        </div>
        """
    return (
        f'<div class="glass-panel rounded-2xl p-5 border border-rose-500/40 bg-rose-950/40 text-rose-200 space-y-2 animate-fade-in">'
        f'  <div class="flex items-center gap-2 text-rose-400 font-bold text-sm">'
        f'    <svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">'
        f'      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />'
        f'    </svg>'
        f'    <span>Generation Could Not Start</span>'
        f'  </div>'
        f'  <p class="text-xs text-rose-200/90 leading-relaxed">{message}</p>'
        f'  {action_html}'
        f'</div>'
    )

@login_required
@require_POST
def create_generation_view(request):
    """
    Manual studio generation endpoint (HTMX / POST).
    Calculates cost, reserves credits with row lock, and dispatches Celery worker task.
    """
    is_staff_or_debug = getattr(settings, 'DEBUG', False) or request.user.is_staff
    gen_type = request.POST.get('generation_type', 'image')
    prompt = request.POST.get('prompt', '').strip()[:2000]
    negative_prompt = request.POST.get('negative_prompt', '').strip()[:1000]
    model_choice = request.POST.get('model', 'automatic')
    aspect_ratio = request.POST.get('aspect_ratio', '16:9')
    voice_choice = request.POST.get('voice', 'adam')
    character_id = request.POST.get('character_id')
    quality = voice_choice if gen_type == 'audio' else request.POST.get('quality', 'standard')

    try:
        duration_raw = request.POST.get('duration', '5')
        if gen_type == 'video':
            duration = int(duration_raw)
            if duration < 3:
                duration = 3
            elif duration > 15:
                duration = 15
        elif gen_type == 'audio':
            duration = int(duration_raw)
            if duration < 1:
                duration = 5
            elif duration > 30:
                duration = 30
        else:
            duration = 0
    except (ValueError, TypeError):
        duration = 5 if gen_type in ('video', 'audio') else 0

    if not prompt:
        return HttpResponse(_render_error_card("Please enter a prompt describing your vision in detail.", is_staff_or_debug=is_staff_or_debug), status=400)

    # Enforce concurrency limit based on user subscription tier
    wallet = CreditService.get_or_create_wallet(request.user)
    active_jobs_count = Generation.objects.filter(
        user=request.user,
        status__in=['queued', 'processing']
    ).count()
    if active_jobs_count >= wallet.max_parallel_generations:
        tier_display = wallet.get_subscription_tier_display()
        return HttpResponse(
            _render_error_card(
                f"Concurrency limit reached ({active_jobs_count}/{wallet.max_parallel_generations} active jobs). "
                f"Your {tier_display} plan allows {wallet.max_parallel_generations} simultaneous generation{'s' if wallet.max_parallel_generations > 1 else ''}. "
                "Please wait for current jobs to finish or upgrade your plan to run more in parallel.",
                is_staff_or_debug=is_staff_or_debug
            ),
            status=429
        )

    # Validate character ownership to prevent IDOR
    valid_character = None
    if character_id:
        valid_character = Character.objects.filter(id=character_id, owner=request.user).first()

    # Reference asset upload with extension and size validation
    ref_media = None
    if 'reference_file' in request.FILES:
        uploaded_file = request.FILES['reference_file']
        ext = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else ''
        if ext not in ALLOWED_REF_EXTENSIONS:
            return HttpResponse(
                _render_error_card(f"Unsupported file type (.{ext}). Allowed formats: {', '.join(sorted(ALLOWED_REF_EXTENSIONS)).upper()}.", is_staff_or_debug=is_staff_or_debug),
                status=400
            )
        if uploaded_file.size > MAX_REF_FILE_SIZE:
            return HttpResponse(_render_error_card("Uploaded file exceeds 25MB limit.", is_staff_or_debug=is_staff_or_debug), status=400)

        ref_media = Media.objects.create(
            owner=request.user,
            media_type='reference',
            file=uploaded_file,
            file_size=uploaded_file.size
        )

    # Select model via ModelRouter
    try:
        selected_model = ModelRouter.select_model(
            modality=gen_type,
            user_preference=model_choice,
            duration=duration,
            aspect_ratio=aspect_ratio,
            requires_image_ref=bool(ref_media)
        )
    except Exception as exc:
        return HttpResponse(_render_error_card(f"Model Routing Error: {exc}", is_staff_or_debug=is_staff_or_debug), status=400)

    # Clamp duration to model max_duration
    if gen_type == 'video':
        max_dur = getattr(selected_model, 'max_duration', 10)
        if duration > max_dur:
            duration = max_dur

    # Calculate credit cost
    credit_cost = selected_model.calculate_credit_cost(duration=duration)

    # Create Generation record
    generation = Generation.objects.create(
        user=request.user,
        generation_type=gen_type,
        provider=selected_model.provider,
        model=selected_model,
        model_id_snapshot=selected_model.model_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        aspect_ratio=aspect_ratio,
        duration=duration,
        quality=quality,
        character=valid_character,
        status='queued'
    )

    if ref_media:
        generation.reference_media.add(ref_media)

    # Atomically reserve credits
    try:
        CreditService.reserve_credits(request.user, credit_cost, generation)
    except Exception as exc:
        generation.status = 'failed'
        generation.error_message = str(exc)
        generation.save(update_fields=['status', 'error_message'])
        return HttpResponse(_render_error_card(str(exc), is_credit_error=True, is_staff_or_debug=is_staff_or_debug), status=400)

    # Dispatch Celery worker task
    dispatch_generation_task.delay(str(generation.id))

    # Return initial status pill / card for HTMX polling
    return render(request, 'partials/generation_status.html', _get_generation_partial_context(generation))

@login_required
def generation_status_partial(request, generation_id):
    """HTMX polling endpoint returning live status and media preview when finished."""
    generation = get_object_or_404(
        Generation.objects.select_related('output_media', 'model', 'provider', 'project'),
        id=generation_id,
        user=request.user
    )
    if generation.status in ('queued', 'processing'):
        from apps.generations.tasks import check_and_update_generation_status
        generation = check_and_update_generation_status(generation)

    return render(request, 'partials/generation_status.html', _get_generation_partial_context(generation))

@login_required
@require_POST
def toggle_favorite_view(request, generation_id):
    gen = get_object_or_404(Generation, id=generation_id, user=request.user)
    gen.is_favorite = not gen.is_favorite
    gen.save(update_fields=['is_favorite'])
    return JsonResponse({"is_favorite": gen.is_favorite})

from apps.ai.dialogue import AIDialogueDirector

@login_required
@require_POST
def deduce_dialogue_api_view(request):
    """
    AJAX / JSON API endpoint to deduce in-character dialogue or foley dynamically using AI.
    """
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST

        prompt = data.get('prompt', '').strip()
        char_name = data.get('character_name', '').strip()
        duration = int(data.get('duration', 5))
        style = data.get('style', 'dialogue')
        gender = data.get('character_gender', '').strip()

        result = AIDialogueDirector.deduce_dialogue(
            prompt=prompt,
            character_name=char_name,
            duration=duration,
            style=style,
            character_gender=gender
        )
        return JsonResponse(result)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

@login_required
@require_POST
def synthesize_video_audio_view(request, generation_id):
    """
    Generate and attach an AI Foley soundtrack or Voiceover to an already generated video.
    """
    parent_gen = get_object_or_404(
        Generation.objects.select_related('output_media', 'model', 'provider', 'project', 'character'),
        id=generation_id,
        user=request.user
    )
    
    audio_type = request.POST.get('audio_type', 'foley')  # 'foley' or 'tts'
    raw_prompt = request.POST.get('audio_prompt', '').strip()
    voice = request.POST.get('voice', 'adam')
    requested_model = request.POST.get('model', 'eleven-sound-effects' if audio_type == 'foley' else 'eleven-multilingual-v2')
    duration = parent_gen.duration or 5
    char_name = parent_gen.character.name if parent_gen.character else ""
    char_gender = getattr(parent_gen.character, 'gender', '')

    if audio_type == 'tts':
        # If user did not provide a bespoke script, dynamically deduce in-character line via AI
        if not raw_prompt or raw_prompt == parent_gen.prompt or any(w in raw_prompt.lower() for w in ['photorealistic', '8k', 'cinematic', 'tracking shot']):
            deduction = AIDialogueDirector.deduce_dialogue(
                prompt=parent_gen.prompt,
                character_name=char_name,
                duration=duration,
                style='dialogue',
                character_gender=char_gender
            )
            audio_prompt = deduction.get('dialogue', '')
            if not voice or voice == 'adam':
                voice = deduction.get('suggested_voice', 'adam')
        else:
            audio_prompt = raw_prompt
    else:
        if not raw_prompt:
            audio_prompt = f"Cinematic atmospheric sound effects, foley, footsteps, and score for: {parent_gen.prompt}"
        else:
            audio_prompt = raw_prompt

    # Resolve audio model
    selected_model = AIModel.objects.filter(model_id=requested_model, is_enabled=True).first()
    if not selected_model:
        selected_model = ModelRouter.select_model(modality='audio', user_preference='automatic', duration=duration)

    credit_cost = selected_model.calculate_credit_cost(duration=duration) if selected_model else 25

    # Check and reserve credits
    try:
        audio_gen = Generation.objects.create(
            user=request.user,
            project=parent_gen.project,
            parent_generation=parent_gen,
            generation_type='audio',
            provider=selected_model.provider,
            model=selected_model,
            model_id_snapshot=selected_model.model_id,
            prompt=audio_prompt,
            quality=voice if audio_type == 'tts' else 'standard',
            duration=duration,
            status='queued'
        )
        if parent_gen.output_media:
            audio_gen.reference_media.add(parent_gen.output_media)

        CreditService.reserve_credits(request.user, credit_cost, audio_gen)
        try:
            dispatch_generation_task(str(audio_gen.id))
        except Exception:
            dispatch_generation_task.delay(str(audio_gen.id))
        parent_gen.refresh_from_db()
    except Exception as exc:
        if request.headers.get('HX-Request'):
            return HttpResponse(_render_error_card(f"Could not synthesize audio: {exc}"), status=400)
        messages.error(request, f"Could not synthesize audio: {exc}")
        return redirect('generations:detail', pk=parent_gen.id)

    if request.headers.get('HX-Request'):
        return render(request, 'partials/generation_status.html', _get_generation_partial_context(parent_gen))
    return redirect('generations:detail', pk=parent_gen.id)

@login_required
@require_POST
def lipsync_video_view(request, generation_id):
    """
    1-Click Neural Lip-Sync: Animates character facial movements and mouth to synchronize with the attached audio.
    """
    parent_gen = get_object_or_404(
        Generation.objects.select_related('output_media', 'audio_track', 'model', 'provider', 'project'),
        id=generation_id,
        user=request.user
    )

    audio_media = parent_gen.latest_audio
    if not audio_media or not parent_gen.output_media:
        err_msg = "Please synthesize or attach an audio track before running Neural Lip-Sync."
        if request.headers.get('HX-Request'):
            return HttpResponse(_render_error_card(err_msg), status=400)
        messages.error(request, err_msg)
        return redirect('generations:detail', pk=parent_gen.id)

    # Resolve or create Lip-Sync AI Model entry
    fal_provider_obj = parent_gen.provider
    lipsync_model = AIModel.objects.filter(model_id='fal-sync-lipsync', is_enabled=True).first()
    if not lipsync_model:
        # Fallback to general video model or create on-the-fly
        from apps.providers.models import AIProviderConfig
        fal_cfg = AIProviderConfig.objects.filter(slug='fal').first() or fal_provider_obj
        lipsync_model, _ = AIModel.objects.get_or_create(
            model_id='fal-sync-lipsync',
            defaults={
                'provider': fal_cfg,
                'display_name': 'SyncLabs LipSync 1.7 (Neural)',
                'modality': 'video',
                'credit_cost_fixed': 15,
                'credit_cost_per_second': 3,
                'is_enabled': True
            }
        )

    duration = parent_gen.duration or 5
    credit_cost = lipsync_model.calculate_credit_cost(duration=duration)

    try:
        lipsync_gen = Generation.objects.create(
            user=request.user,
            project=parent_gen.project,
            parent_generation=parent_gen,
            generation_type='video',
            provider=lipsync_model.provider,
            model=lipsync_model,
            model_id_snapshot=lipsync_model.model_id,
            prompt=f"👄 Neural Lip-Sync: {parent_gen.prompt}",
            aspect_ratio=parent_gen.aspect_ratio,
            duration=duration,
            quality=parent_gen.quality,
            character=parent_gen.character,
            audio_track=audio_media,
            status='queued'
        )
        lipsync_gen.reference_media.add(parent_gen.output_media)
        lipsync_gen.reference_media.add(audio_media)

        CreditService.reserve_credits(request.user, credit_cost, lipsync_gen)
        try:
            dispatch_generation_task(str(lipsync_gen.id))
        except Exception:
            dispatch_generation_task.delay(str(lipsync_gen.id))
    except Exception as exc:

        if request.headers.get('HX-Request'):
            return HttpResponse(_render_error_card(f"Could not start Neural Lip-Sync: {exc}"), status=400)
        messages.error(request, f"Could not start Neural Lip-Sync: {exc}")
        return redirect('generations:detail', pk=parent_gen.id)

    if request.headers.get('HX-Request'):
        return render(request, 'partials/generation_status.html', _get_generation_partial_context(lipsync_gen))
    return redirect('generations:detail', pk=lipsync_gen.id)
