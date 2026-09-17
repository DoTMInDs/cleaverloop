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

@login_required
@require_POST
def create_generation_view(request):
    """
    Manual studio generation endpoint (HTMX / POST).
    Calculates cost, reserves credits with row lock, and dispatches Celery worker task.
    """
    gen_type = request.POST.get('generation_type', 'image')
    prompt = request.POST.get('prompt', '').strip()
    negative_prompt = request.POST.get('negative_prompt', '').strip()
    model_choice = request.POST.get('model', 'automatic')
    aspect_ratio = request.POST.get('aspect_ratio', '16:9')
    duration = int(request.POST.get('duration', 5)) if gen_type == 'video' else 0
    quality = request.POST.get('quality', 'standard')
    character_id = request.POST.get('character_id')

    if not prompt:
        return HttpResponse("<div class='p-3 bg-rose-500/20 text-rose-300 rounded-lg text-sm'>Please enter a prompt.</div>", status=400)

    # Reference asset upload if provided
    ref_media = None
    if 'reference_file' in request.FILES:
        uploaded_file = request.FILES['reference_file']
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
        return HttpResponse(f"<div class='p-3 bg-rose-500/20 text-rose-300 rounded-lg text-sm'>{exc}</div>", status=400)

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
        character_id=character_id or None,
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
        return HttpResponse(f"<div class='p-3 bg-rose-500/20 text-rose-300 rounded-lg text-sm'>{exc}</div>", status=400)

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
