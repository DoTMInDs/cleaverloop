from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
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
        return ctx

@login_required
@require_POST
def generate_scene_view(request, scene_id):
    """Trigger AI generation for an individual storyboard scene."""
    scene = get_object_or_404(Scene, id=scene_id, project__owner=request.user)
    project = scene.project

    # Use ModelRouter to select video model
    model = ModelRouter.select_model(
        modality='video',
        user_preference='automatic',
        duration=scene.duration,
        aspect_ratio=project.aspect_ratio
    )
    credit_cost = model.calculate_credit_cost(scene.duration)

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
