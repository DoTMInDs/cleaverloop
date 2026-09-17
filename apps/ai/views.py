import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from apps.ai.agent import SuperAgent
from apps.ai.safety import AgentSafetyValidator
from apps.credits.services import CreditService
from apps.projects.models import Project, Scene
from apps.generations.models import Generation
from apps.providers.router import ModelRouter
from apps.generations.tasks import dispatch_generation_task

@login_required
def super_agent_page_view(request):
    """Super Agent natural language generation interface."""
    wallet = CreditService.get_or_create_wallet(request.user)
    return render(request, 'studio/super_agent.html', {'wallet': wallet})

@login_required
@require_POST
def plan_agent_brief_view(request):
    """Decomposes a user prompt into a structured plan for review."""
    prompt = request.POST.get('prompt', '').strip()
    aspect_ratio = request.POST.get('aspect_ratio', '16:9')

    if not prompt:
        return HttpResponse("<div class='text-rose-400 p-3'>Please provide a description of what you want to create.</div>", status=400)

    try:
        plan = SuperAgent.decompose_idea(prompt=prompt, target_aspect_ratio=aspect_ratio)
        wallet = CreditService.get_or_create_wallet(request.user)
        AgentSafetyValidator.validate_plan(plan, wallet)
    except Exception as exc:
        return HttpResponse(f"<div class='p-3 bg-rose-500/20 text-rose-300 rounded-lg text-sm'>{exc}</div>", status=400)

    # Return structured storyboard review card
    return render(request, 'partials/agent_plan_card.html', {'plan': plan, 'plan_json': plan.model_dump_json()})

@login_required
@require_POST
def execute_agent_plan_view(request):
    """Executes an approved plan: creates Project, Scenes, Generation records, and queues Celery workers."""
    plan_json = request.POST.get('plan_data', '')
    if not plan_json:
        return HttpResponse("Missing plan data.", status=400)

    try:
        data = json.loads(plan_json)
        project = Project.objects.create(
            owner=request.user,
            name=data.get('project_title', 'AI Super Agent Project'),
            description=data.get('project_description', ''),
            aspect_ratio=data.get('aspect_ratio', '16:9'),
            status='active'
        )

        for scene_data in data.get('scenes', []):
            scene = Scene.objects.create(
                project=project,
                order=scene_data.get('order', 1),
                title=scene_data.get('title', 'Scene'),
                prompt=scene_data.get('prompt', ''),
                duration=scene_data.get('duration', 5),
                camera_direction=scene_data.get('camera_direction', ''),
                visual_style=scene_data.get('visual_style', ''),
                dialogue=scene_data.get('dialogue', ''),
                status='queued'
            )

            # Auto-route and reserve
            model = ModelRouter.select_model(
                modality='video',
                user_preference='automatic',
                duration=scene.duration,
                aspect_ratio=project.aspect_ratio
            )
            cost = model.calculate_credit_cost(scene.duration)

            gen = Generation.objects.create(
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

            CreditService.reserve_credits(request.user, cost, gen)
            dispatch_generation_task.delay(str(gen.id))

        return redirect('projects:detail', pk=project.pk)

    except Exception as exc:
        return HttpResponse(f"<div class='p-3 bg-rose-500/20 text-rose-300 rounded-lg'>{exc}</div>", status=400)
