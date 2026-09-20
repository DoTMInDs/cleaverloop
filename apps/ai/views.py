import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from apps.ai.schemas import StoryboardPlan
from apps.ai.agent import SuperAgent
from apps.ai.safety import AgentSafetyValidator
from apps.credits.services import CreditService
from apps.projects.models import Project, Scene
from apps.generations.models import Generation
from apps.characters.models import Character
from apps.providers.router import ModelRouter
from apps.generations.tasks import dispatch_generation_task

@login_required
def super_agent_page_view(request):
    """Super Agent natural language generation interface with character roster."""
    wallet = CreditService.get_or_create_wallet(request.user)
    characters = Character.objects.filter(owner=request.user).order_by('-updated_at')
    recent_projects = Project.objects.filter(owner=request.user).prefetch_related('scenes').order_by('-created_at')[:4]
    return render(request, 'studio/super_agent.html', {
        'wallet': wallet,
        'characters': characters,
        'recent_projects': recent_projects
    })

@login_required
@require_POST
def plan_agent_brief_view(request):
    """Decomposes a user prompt into a structured plan for review with consistent character cast."""
    prompt = request.POST.get('prompt', '').strip()
    aspect_ratio = request.POST.get('aspect_ratio', '16:9')
    character_id = request.POST.get('character_id', '').strip()

    if not prompt:
        return HttpResponse("<div class='text-rose-400 p-3'>Please provide a description of what you want to create.</div>", status=400)

    character = None
    if character_id:
        try:
            character = Character.objects.filter(id=character_id, owner=request.user).first()
        except Exception:
            character = None

    try:
        plan = SuperAgent.decompose_idea(prompt=prompt, target_aspect_ratio=aspect_ratio, character=character)
        wallet = CreditService.get_or_create_wallet(request.user)
        AgentSafetyValidator.validate_plan(plan, wallet)
    except Exception as exc:
        return HttpResponse(f"<div class='p-3 bg-rose-500/20 text-rose-300 rounded-lg text-sm'>{exc}</div>", status=400)

    # Return structured storyboard review card
    return render(request, 'partials/agent_plan_card.html', {'plan': plan, 'plan_json': plan.model_dump_json()})

@login_required
@require_POST
def execute_agent_plan_view(request):
    """Executes an approved plan: validates safety constraints, creates Project/Scenes/Generations atomically with characters, and queues Celery workers."""
    plan_json = request.POST.get('plan_data', '')
    if not plan_json:
        return HttpResponse("Missing plan data.", status=400)

    try:
        data = json.loads(plan_json)
        # 1. Strictly re-validate client-submitted plan against Pydantic schema
        plan = StoryboardPlan(**data)

        # 2. Re-validate budget, scene limits, and wallet balance
        wallet = CreditService.get_or_create_wallet(request.user)
        AgentSafetyValidator.validate_plan(plan, wallet)

        # Resolve selected character if attached
        attached_character = None
        if plan.selected_character_id:
            try:
                attached_character = Character.objects.filter(id=plan.selected_character_id, owner=request.user).first()
            except Exception:
                attached_character = None

        # 3. Atomically create all records and reserve credits
        dispatched_gen_ids = []
        with transaction.atomic():
            project = Project.objects.create(
                owner=request.user,
                name=plan.project_title or 'AI Super Agent Project',
                description=plan.project_description or '',
                aspect_ratio=plan.aspect_ratio or '16:9',
                status='active'
            )

            for scene_data in plan.scenes:
                scene = Scene.objects.create(
                    project=project,
                    order=scene_data.order,
                    title=scene_data.title or f"Scene {scene_data.order}",
                    prompt=scene_data.prompt,
                    duration=scene_data.duration,
                    camera_direction=scene_data.camera_direction or '',
                    visual_style=scene_data.visual_style or '',
                    dialogue=scene_data.dialogue or '',
                    status='queued'
                )

                if attached_character:
                    scene.characters.add(attached_character)

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
                    character=attached_character,
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
                dispatched_gen_ids.append(str(gen.id))

        # 4. Dispatch Celery tasks only after transaction successfully commits
        for gen_id in dispatched_gen_ids:
            dispatch_generation_task.delay(gen_id)

        return redirect('projects:detail', pk=project.pk)

    except Exception as exc:
        return HttpResponse(f"<div class='p-3 bg-rose-500/20 text-rose-300 rounded-lg'>{exc}</div>", status=400)
