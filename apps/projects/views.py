from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from apps.projects.models import Project, Scene
from apps.generations.models import Generation
from apps.providers.router import ModelRouter
from apps.credits.services import CreditService
from apps.generations.tasks import dispatch_generation_task
from apps.editor.models import AssemblyJob
from apps.editor.tasks import assemble_project_video_task

class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'projects/list.html'
    context_object_name = 'projects'

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

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

    # Use ModelRouter to select video model
    try:
        model = ModelRouter.select_model(
            modality='video',
            user_preference='automatic',
            duration=scene.duration,
            aspect_ratio=project.aspect_ratio
        )
    except Exception as exc:
        return HttpResponse(f"<div class='text-rose-400 p-2 text-xs'>Model routing error: {exc}</div>", status=400)

    credit_cost = model.calculate_credit_cost(scene.duration)
    is_allowed, eff_cost, msg = CreditService.can_generate(request.user, credit_cost, modality='video')
    if not is_allowed:
        return HttpResponse(f"<div class='text-rose-400 p-2 text-xs'>{msg}</div>", status=400)

    generation = Generation.objects.create(
        user=request.user,
        project=project,
        scene=scene,
        generation_type='video',
        provider=model.provider,
        model=model,
        model_id_snapshot=model.model_id,
        prompt=scene.prompt,
        duration=scene.duration,
        aspect_ratio=project.aspect_ratio,
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
        return HttpResponse("<div class='text-rose-400 p-2 text-sm'>No completed scenes available to assemble. Generate scenes first!</div>", status=400)

    job = AssemblyJob.objects.create(
        project=project,
        user=request.user,
        target_aspect_ratio=project.aspect_ratio,
        status='queued'
    )
    project.status = 'rendering'
    project.save(update_fields=['status'])

    assemble_project_video_task.delay(str(job.id))
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

    Scene.objects.create(
        project=project,
        order=next_order,
        title=title,
        prompt=prompt,
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
