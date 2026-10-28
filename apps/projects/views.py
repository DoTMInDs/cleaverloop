import os
import logging
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404

logger = logging.getLogger(__name__)
from django.views.generic import ListView, DetailView, CreateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from apps.projects.models import Project, Scene, CinemaLook
from apps.projects.cinema_recipes import get_cinema_catalog, build_director_prompt_modifier
from apps.media.models import Media
from apps.generations.models import Generation
from apps.providers.router import ModelRouter
from apps.credits.services import CreditService
from apps.generations.tasks import dispatch_generation_task
from apps.editor.models import AssemblyJob
from apps.editor.tasks import assemble_project_video_task
from apps.editor.ffmpeg_service import FFmpegService

class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'projects/list.html'
    context_object_name = 'projects'

    def get_queryset(self):
        qs = Project.objects.filter(owner=self.request.user)
        tab = self.request.GET.get('tab', 'all')
        if tab == 'favorites':
            qs = qs.filter(is_favorite=True, is_trashed=False)
        elif tab == 'trash':
            qs = qs.filter(is_trashed=True)
        else:
            qs = qs.filter(is_trashed=False)

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_qs = Project.objects.filter(owner=self.request.user)
        ctx['active_tab'] = self.request.GET.get('tab', 'all')
        ctx['search_query'] = self.request.GET.get('q', '').strip()
        ctx['all_count'] = base_qs.filter(is_trashed=False).count()
        ctx['favorites_count'] = base_qs.filter(is_favorite=True, is_trashed=False).count()
        ctx['trash_count'] = base_qs.filter(is_trashed=True).count()
        return ctx

class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    fields = ['name', 'description', 'aspect_ratio']
    template_name = 'projects/create.html'

    def form_valid(self, form):
        form.instance.owner = self.request.user
        project = form.save()
        # Seed 2 starter scenes for the new project
        Scene.objects.create(
            project=project,
            order=1,
            title="Scene 1: Introduction",
            prompt=f"Cinematic introduction scene for {project.name}. High quality, photorealistic, 4k.",
            duration=5
        )
        Scene.objects.create(
            project=project,
            order=2,
            title="Scene 2: Core Narrative",
            prompt=f"Dynamic central action sequence for {project.name}.",
            duration=5
        )
        return redirect('projects:detail', pk=project.pk)

class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = 'projects/detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['scenes'] = self.object.scenes.select_related('generated_media').prefetch_related('characters').all()
        ctx['cinema_catalog'] = get_cinema_catalog()
        ctx['saved_looks'] = CinemaLook.objects.filter(owner=self.request.user)
        if self.object.status == 'rendering':
            ctx['active_assembly_job'] = AssemblyJob.objects.filter(
                project=self.object,
                user=self.request.user,
                status__in=('queued', 'rendering')
            ).order_by('-created_at').first()
        else:
            ctx['active_assembly_job'] = None
        return ctx

class ProjectDeleteView(LoginRequiredMixin, DeleteView):
    model = Project
    success_url = reverse_lazy('projects:list')

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

    def delete(self, request, *args, **kwargs):
        project = self.get_object()
        messages.success(request, f"Project '{project.name}' was deleted.")
        return super().delete(request, *args, **kwargs)

@login_required
@require_POST
def generate_scene_view(request, scene_id):
    """Trigger AI generation for an individual storyboard scene."""
    scene = get_object_or_404(Scene, id=scene_id, project__owner=request.user)
    project = scene.project

    # Check concurrency limits based on tier
    wallet = CreditService.get_or_create_wallet(request.user)
    active_jobs = Generation.objects.filter(
        user=request.user,
        status__in=['queued', 'processing']
    ).count()
    if active_jobs >= wallet.max_parallel_generations:
        return HttpResponse(
            f"<div class='text-rose-400 p-2 text-xs'>Concurrency limit reached ({active_jobs}/{wallet.max_parallel_generations} active jobs). Please wait for ongoing jobs to complete.</div>",
            status=429
        )

    # Use ModelRouter to select video model with user tier context
    try:
        model = ModelRouter.select_model(
            modality='video',
            user_preference='automatic',
            duration=scene.duration,
            aspect_ratio=project.aspect_ratio,
            user=request.user,
        )
    except Exception as exc:
        return HttpResponse(f"<div class='text-rose-400 p-2 text-xs'>Model routing error: {exc}</div>", status=400)

    credit_cost = model.calculate_credit_cost(scene.duration)
    is_allowed, eff_cost, msg = CreditService.can_generate(request.user, credit_cost, modality='video')
    if not is_allowed:
        return HttpResponse(f"<div class='text-rose-400 p-2 text-xs'>{msg}</div>", status=400)

    merged_recipe = {}
    if project.director_settings:
        merged_recipe.update(project.director_settings)
    if scene.director_recipe:
        merged_recipe.update(scene.director_recipe)
    director_cue = build_director_prompt_modifier(merged_recipe)
    effective_prompt = f"{scene.prompt}. {director_cue}" if director_cue else scene.prompt

    generation = Generation.objects.create(
        user=request.user,
        project=project,
        scene=scene,
        generation_type='video',
        provider=model.provider,
        model=model,
        model_id_snapshot=model.model_id,
        prompt=effective_prompt,
        duration=scene.duration,
        aspect_ratio=project.aspect_ratio,
        quality='standard' if scene.is_draft else 'hd',
        status='queued'
    )

    try:
        CreditService.reserve_credits(request.user, credit_cost, generation)
    except Exception as e:
        generation.status = 'failed'
        generation.error_message = str(e)
        generation.save(update_fields=['status', 'error_message'])
        return HttpResponse(f"<div class='text-rose-400 p-2 text-xs'>Failed: {e}</div>", status=400)

    scene.status = 'queued'
    scene.save(update_fields=['status'])

    # Dispatch Celery async task
    dispatch_generation_task.delay(str(generation.id))

    # Return HTMX scene item fragment
    return render(request, 'partials/scene_item.html', {'scene': scene, 'project': project})

@login_required
@require_POST
def assemble_project_view(request, project_id):
    """Trigger video concatenation and rendering across all completed scenes."""
    project = get_object_or_404(Project, id=project_id, owner=request.user)

    completed_scenes = project.scenes.filter(generated_media__isnull=False)
    if not completed_scenes.exists():
        messages.error(request, "No completed scenes available to assemble. Render or upload video scenes first!")
        return redirect('projects:detail', pk=project.pk)

    bgm_id = request.POST.get('background_music')
    bgm_media = None
    if bgm_id:
        bgm_media = Media.objects.filter(id=bgm_id, owner=request.user, media_type='audio').first()

    # Direct audio file upload for soundtrack
    bgm_file = request.FILES.get('bgm_file')
    if bgm_file:
        try:
            bgm_media = Media.objects.create(
                owner=request.user,
                project=project,
                media_type='audio',
                file=bgm_file,
                file_size=bgm_file.size,
                mime_type=bgm_file.content_type or 'audio/mpeg'
            )
        except Exception as exc:
            logger.warning(f"Could not save BGM upload: {exc}")

    target_aspect = request.POST.get('target_aspect_ratio') or project.aspect_ratio

    job = AssemblyJob.objects.create(
        project=project,
        user=request.user,
        target_aspect_ratio=target_aspect,
        background_music=bgm_media,
        status='queued'
    )
    project.status = 'rendering'
    project.save(update_fields=['status'])

    assemble_project_video_task.delay(str(job.id))
    messages.info(request, f"Started film assembly for '{project.name}' with intelligent normalization.")
    return redirect('projects:detail', pk=project.pk)

@login_required
@require_POST
def add_scene_view(request, project_id):
    """Add a new scene to an existing storyboard project."""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    next_order = (project.scenes.order_by('-order').values_list('order', flat=True).first() or 0) + 1
    title = request.POST.get('title', '').strip() or f"Scene {next_order}"
    prompt = request.POST.get('prompt', '').strip() or f"Dynamic scene sequence {next_order} for {project.name}."
    try:
        duration = int(request.POST.get('duration', 5))
    except (ValueError, TypeError):
        duration = 5

    camera_direction = request.POST.get('camera_direction', '').strip()
    visual_style = request.POST.get('visual_style', '').strip()
    dialogue = request.POST.get('dialogue', '').strip()
    is_draft = request.POST.get('is_draft', 'true').lower() not in ('false', '0', 'no')

    director_recipe = {}
    for key in ('genre', 'era', 'camera_body', 'lens', 'aperture', 'camera_movement', 'color_palette', 'lighting'):
        val = request.POST.get(key, '').strip()
        if val:
            director_recipe[key] = val
    if not camera_direction and director_recipe.get('camera_movement'):
        camera_direction = director_recipe['camera_movement']
    if not visual_style and director_recipe.get('color_palette'):
        visual_style = director_recipe['color_palette']

    Scene.objects.create(
        project=project,
        order=next_order,
        title=title,
        prompt=prompt,
        camera_direction=camera_direction,
        visual_style=visual_style,
        dialogue=dialogue,
        is_draft=is_draft,
        resolution='480p' if is_draft else '1080p',
        director_recipe=director_recipe or (project.director_settings or {}),
        duration=max(1, min(duration, 10))
    )
    messages.success(request, f"Added Scene {next_order} to {project.name}.")
    return redirect('projects:detail', pk=project.pk)

@login_required
@require_POST
def delete_scene_view(request, scene_id):
    """Delete an individual scene from a project."""
    scene = get_object_or_404(Scene, id=scene_id, project__owner=request.user)
    project_pk = scene.project.pk
    scene_order = scene.order
    scene.delete()
    messages.success(request, f"Scene {scene_order} deleted.")
    return redirect('projects:detail', pk=project_pk)

@login_required
def scene_status_view(request, scene_id):
    """HTMX polling endpoint returning updated scene item card."""
    scene = get_object_or_404(Scene, id=scene_id, project__owner=request.user)
    return render(request, 'partials/scene_item.html', {'scene': scene, 'project': scene.project})

@login_required
@require_POST
def generate_scene_audio_view(request, scene_id):
    """Trigger AI foley sound effects or voiceover synthesis for a storyboard scene."""
    scene = get_object_or_404(Scene, id=scene_id, project__owner=request.user)
    project = scene.project
    audio_type = request.POST.get('audio_type', 'foley')  # 'foley' or 'tts'
    requested_model = request.POST.get('model')

    if requested_model:
        target_model_id = requested_model
    else:
        target_model_id = 'eleven-sound-effects' if audio_type == 'foley' else 'eleven-multilingual-v2'
    
    # Find active audio model
    from apps.providers.models import AIModel
    model = AIModel.objects.filter(model_id=target_model_id, is_enabled=True).first()
    if not model:
        # Fallback to secondary audio models
        fallback_id = 'eleven-sound-effects' if audio_type == 'foley' else 'eleven-turbo-v2'
        model = AIModel.objects.filter(model_id=fallback_id, is_enabled=True).first()
        if not model:
            model = AIModel.objects.filter(modality='audio', is_enabled=True).first()

    credit_cost = model.calculate_credit_cost(scene.duration) if model else 25
    is_allowed, eff_cost, msg = CreditService.can_generate(request.user, credit_cost, modality='audio')
    if not is_allowed:
        return HttpResponse(f"<div class='text-rose-400 p-2 text-xs font-mono'>{msg}</div>", status=400)

    prompt = scene.dialogue if (audio_type == 'tts' and scene.dialogue) else (scene.audio_direction or f"Cinematic atmospheric sound effects and foley for: {scene.prompt}")
    voice = request.POST.get('voice', 'adam')

    generation = Generation.objects.create(
        user=request.user,
        project=project,
        scene=scene,
        generation_type='audio',
        provider=model.provider,
        model=model,
        model_id_snapshot=model.model_id,
        prompt=prompt,
        quality=voice if audio_type == 'tts' else 'standard',
        duration=scene.duration,
        status='queued'
    )

    if scene.generated_media:
        generation.reference_media.add(scene.generated_media)

    try:
        CreditService.reserve_credits(request.user, credit_cost, generation)
    except Exception as e:
        generation.status = 'failed'
        generation.error_message = str(e)
        generation.save(update_fields=['status', 'error_message'])
        return HttpResponse(f"<div class='text-rose-400 p-2 text-xs font-mono'>Failed: {e}</div>", status=400)

    scene.status = 'processing'
    scene.save(update_fields=['status'])

    # Dispatch task
    dispatch_generation_task.delay(str(generation.id))

    return render(request, 'partials/scene_item.html', {'scene': scene, 'project': project})


@login_required
@require_POST
def upload_scene_video_view(request, scene_id):
    """Allow user to directly upload a custom video file into a storyboard scene."""
    scene = get_object_or_404(Scene, id=scene_id, project__owner=request.user)
    project = scene.project

    video_file = request.FILES.get('video_file')
    if not video_file:
        messages.error(request, "No video file was uploaded.")
        return redirect('projects:detail', pk=project.pk)

    # Basic format validation
    allowed_exts = ('.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v')
    ext = os.path.splitext(video_file.name)[1].lower()
    if ext not in allowed_exts:
        messages.error(request, f"Unsupported video file type ({ext}). Allowed: MP4, MOV, WebM, AVI, MKV.")
        return redirect('projects:detail', pk=project.pk)

    # File size limit check (250MB)
    if video_file.size > 250 * 1024 * 1024:
        messages.error(request, "Uploaded video exceeds the 250MB maximum size limit.")
        return redirect('projects:detail', pk=project.pk)

    try:
        media = Media.objects.create(
            owner=request.user,
            project=project,
            media_type='video',
            file=video_file,
            file_size=video_file.size,
            mime_type=video_file.content_type or 'video/mp4'
        )

        # Probe video to extract actual duration and dimensions
        if media.file and os.path.exists(media.file.path):
            probe = FFmpegService.probe_clip(media.file.path)
            media.width = probe.get('width', 1920)
            media.height = probe.get('height', 1080)
            media.duration = probe.get('duration', 5.0)
            media.save(update_fields=['width', 'height', 'duration'])
            scene.duration = max(1, int(round(probe.get('duration', 5.0))))

        scene.generated_media = media
        scene.status = 'completed'
        scene.save(update_fields=['generated_media', 'status', 'duration'])

        messages.success(request, f"Uploaded custom video to Scene 0{scene.order} successfully.")
    except Exception as exc:
        messages.error(request, f"Failed to process uploaded video: {exc}")

    if request.headers.get('HX-Request'):
        return render(request, 'partials/scene_item.html', {'scene': scene, 'project': project})

    return redirect('projects:detail', pk=project.pk)


@login_required
def reorder_scene_view(request, scene_id, direction):
    """Reorder a scene up or down within its project storyboard sequence."""
    scene = get_object_or_404(Scene, id=scene_id, project__owner=request.user)
    project = scene.project

    with transaction.atomic():
        if direction == 'up':
            target_scene = project.scenes.filter(order__lt=scene.order).order_by('-order').first()
        elif direction == 'down':
            target_scene = project.scenes.filter(order__gt=scene.order).order_by('order').first()
        else:
            target_scene = None

        if target_scene:
            orig_scene_order = scene.order
            target_order = target_scene.order

            # Temporary order to avoid unique_together constraint collision
            temp_order = 999999
            scene.order = temp_order
            scene.save(update_fields=['order'])

            target_scene.order = orig_scene_order
            target_scene.save(update_fields=['order'])

            scene.order = target_order
            scene.save(update_fields=['order'])

            messages.success(request, f"Moved Scene {orig_scene_order} to position {target_order}.")

    return redirect('projects:detail', pk=project.pk)


@login_required
@require_POST
def batch_upload_scenes_view(request, project_id):
    """Upload multiple video clips at once to automatically create sequential storyboard scenes."""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    files = request.FILES.getlist('video_files')
    if not files:
        messages.error(request, "No video files were selected.")
        return redirect('projects:detail', pk=project.pk)

    allowed_exts = ('.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v')
    created_count = 0

    for f in files:
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in allowed_exts:
            continue
        if f.size > 250 * 1024 * 1024:
            continue

        try:
            media = Media.objects.create(
                owner=request.user,
                project=project,
                media_type='video',
                file=f,
                file_size=f.size,
                mime_type=f.content_type or 'video/mp4'
            )

            probe_dur = 5
            if media.file and os.path.exists(media.file.path):
                probe = FFmpegService.probe_clip(media.file.path)
                media.width = probe.get('width', 1920)
                media.height = probe.get('height', 1080)
                media.duration = probe.get('duration', 5.0)
                media.save(update_fields=['width', 'height', 'duration'])
                probe_dur = max(1, int(round(probe.get('duration', 5.0))))

            next_order = (project.scenes.order_by('-order').values_list('order', flat=True).first() or 0) + 1
            stem_title = os.path.splitext(f.name)[0].replace('_', ' ').replace('-', ' ').title()

            Scene.objects.create(
                project=project,
                order=next_order,
                title=f"Scene {next_order}: {stem_title[:60]}",
                prompt=f"Uploaded video clip: {stem_title}",
                duration=probe_dur,
                generated_media=media,
                status='completed'
            )
            created_count += 1
        except Exception as exc:
            logger.error(f"Error in batch upload for {f.name}: {exc}")

    if created_count > 0:
        messages.success(request, f"Successfully imported {created_count} video clip{'s' if created_count != 1 else ''} into your storyboard!")
    else:
        messages.error(request, "Could not upload files. Ensure they are valid video files (MP4, MOV, WebM, AVI).")

    return redirect('projects:detail', pk=project.pk)


@login_required
@require_POST
def toggle_project_favorite_view(request, pk):
    """Toggle favorite star status on a project."""
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    project.is_favorite = not project.is_favorite
    project.save(update_fields=['is_favorite', 'updated_at'])
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'success': True, 'is_favorite': project.is_favorite})
    return redirect(request.META.get('HTTP_REFERER') or reverse('projects:list'))


@login_required
@require_POST
def toggle_project_trash_view(request, pk):
    """Move a project to trash or restore it from trash."""
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    project.is_trashed = not project.is_trashed
    project.save(update_fields=['is_trashed', 'updated_at'])
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'success': True, 'is_trashed': project.is_trashed})
    messages.info(request, f"Project '{project.name}' {'moved to Trash' if project.is_trashed else 'restored from Trash'}.")
    return redirect(request.META.get('HTTP_REFERER') or reverse('projects:list'))


@login_required
@require_POST
def save_cinema_look_view(request, project_id):
    """Save Cinema Director camera, lens, lighting, and color recipe to the project and optionally as a reusable Look."""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    recipe = {}
    for key in ('genre', 'era', 'camera_body', 'lens', 'aperture', 'camera_movement', 'color_palette', 'lighting'):
        val = request.POST.get(key, '').strip()
        if val:
            recipe[key] = val

    project.director_settings = recipe
    project.save(update_fields=['director_settings', 'updated_at'])

    look_name = request.POST.get('look_name', '').strip()
    saved_look = None
    if look_name and recipe:
        saved_look = CinemaLook.objects.create(
            owner=request.user,
            name=look_name,
            recipe=recipe,
        )

    if request.POST.get('apply_to_all_scenes') in ('1', 'true', 'on'):
        for sc in project.scenes.all():
            sc.director_recipe = recipe
            if recipe.get('camera_movement'):
                sc.camera_direction = recipe['camera_movement']
            if recipe.get('color_palette'):
                sc.visual_style = recipe['color_palette']
            sc.save(update_fields=['director_recipe', 'camera_direction', 'visual_style', 'updated_at'])

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({
            'success': True,
            'recipe': recipe,
            'look_id': str(saved_look.id) if saved_look else None,
            'prompt_modifier': build_director_prompt_modifier(recipe),
        })

    messages.success(request, f"Cinema Director recipe {'and saved look ' + repr(look_name) + ' ' if saved_look else ''}applied to '{project.name}'.")
    return redirect('projects:detail', pk=project.pk)


@login_required
@require_POST
def apply_cinema_look_view(request, project_id, look_id):
    """Apply a previously saved CinemaLook preset to a project and its scenes."""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    look = get_object_or_404(CinemaLook, id=look_id, owner=request.user)
    project.director_settings = look.recipe
    project.save(update_fields=['director_settings', 'updated_at'])

    for sc in project.scenes.all():
        sc.director_recipe = look.recipe
        sc.save(update_fields=['director_recipe', 'updated_at'])

    messages.success(request, f"Applied saved look '{look.name}' across '{project.name}'.")
    return redirect('projects:detail', pk=project.pk)


@login_required
@require_POST
def finalize_scene_take_view(request, scene_id):
    """Promote a 480p draft scene take to 1080p finalized master resolution and trigger HD render."""
    scene = get_object_or_404(Scene, id=scene_id, project__owner=request.user)
    scene.is_draft = False
    scene.resolution = '1080p'
    scene.save(update_fields=['is_draft', 'resolution', 'updated_at'])
    return generate_scene_view(request, scene_id)


