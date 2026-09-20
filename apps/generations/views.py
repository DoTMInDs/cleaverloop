import json
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from apps.generations.models import Generation
from apps.providers.models import AIModel
from apps.providers.router import ModelRouter
from apps.credits.services import CreditService
from apps.generations.tasks import dispatch_generation_task
from apps.media.models import Media
from apps.characters.models import Character

ALLOWED_REF_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'mp4', 'mov'}
MAX_REF_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

class GenerationHistoryView(LoginRequiredMixin, ListView):
    model = Generation
    template_name = 'studio/history.html'
    context_object_name = 'generations'
    paginate_by = 24

    def get_queryset(self):
        qs = Generation.objects.filter(user=self.request.user).select_related('output_media', 'model', 'provider')
        filter_type = self.request.GET.get('type')
        if filter_type in ('image', 'video'):
            qs = qs.filter(generation_type=filter_type)
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

from django.conf import settings

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
    quality = request.POST.get('quality', 'standard')
    character_id = request.POST.get('character_id')

    try:
        duration_raw = request.POST.get('duration', '5')
        duration = int(duration_raw) if gen_type == 'video' else 0
        if duration < 1 and gen_type == 'video':
            duration = 5
    except (ValueError, TypeError):
        duration = 5 if gen_type == 'video' else 0

    if not prompt:
        return HttpResponse(_render_error_card("Please enter a prompt describing your vision in detail.", is_staff_or_debug=is_staff_or_debug), status=400)

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
    return render(request, 'partials/generation_status.html', {'generation': generation})

@login_required
def generation_status_partial(request, generation_id):
    """HTMX polling endpoint returning live status and media preview when finished."""
    generation = get_object_or_404(Generation, id=generation_id, user=request.user)
    return render(request, 'partials/generation_status.html', {'generation': generation})

@login_required
@require_POST
def toggle_favorite_view(request, generation_id):
    gen = get_object_or_404(Generation, id=generation_id, user=request.user)
    gen.is_favorite = not gen.is_favorite
    gen.save(update_fields=['is_favorite'])
    return JsonResponse({"is_favorite": gen.is_favorite})
