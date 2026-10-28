import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.db import transaction
from apps.ai.schemas import StoryboardPlan
from apps.ai.agent import SuperAgent
from apps.ai.safety import AgentSafetyValidator
from apps.ai.models import (
    AgentConversation,
    AgentMessage,
    ViralEffectTemplate,
    DEFAULT_AGENT_SKILLS,
)
from apps.credits.services import CreditService
from apps.projects.models import Project, Scene
from apps.generations.models import Generation
from apps.characters.models import Character
from apps.providers.router import ModelRouter
from apps.generations.tasks import dispatch_generation_task

@login_required
def super_agent_page_view(request):
    """Super Agent natural language generation interface with character roster, skills, conversations & viral effects."""
    wallet = CreditService.get_or_create_wallet(request.user)
    characters = Character.objects.filter(owner=request.user).order_by('-updated_at')
    recent_projects = Project.objects.filter(owner=request.user).prefetch_related('scenes').order_by('-created_at')[:4]
    conversations = AgentConversation.objects.filter(user=request.user).select_related('project', 'character')[:8]
    viral_effects = ViralEffectTemplate.ensure_seeded()
    return render(request, 'studio/super_agent.html', {
        'wallet': wallet,
        'characters': characters,
        'recent_projects': recent_projects,
        'conversations': conversations,
        'agent_skills': DEFAULT_AGENT_SKILLS,
        'viral_effects': viral_effects,
    })

@login_required
@require_POST
def plan_agent_brief_view(request):
    """Decomposes a user prompt into a structured plan for review with consistent character cast, skill preset, and clarifying Q&A."""
    prompt = request.POST.get('prompt', '').strip()
    aspect_ratio = request.POST.get('aspect_ratio', '16:9')
    character_id = request.POST.get('character_id', '').strip()
    skill_preset = request.POST.get('skill_preset', 'general').strip() or 'general'
    conversation_id = request.POST.get('conversation_id', '').strip()

    clarifying_answers = {
        k: request.POST.get(k, '').strip()
        for k in ('visual_tone', 'pacing_style', 'narrative_focus')
        if request.POST.get(k, '').strip()
    }

    if not prompt:
        return HttpResponse("<div class='p-4 bg-rose-500/20 border border-rose-500/30 text-rose-300 rounded-2xl text-sm'>Please provide a description of what you want to create.</div>")

    character = None
    if character_id:
        try:
            character = Character.objects.filter(id=character_id, owner=request.user).first()
        except Exception:
            character = None

    try:
        clarifying_questions = SuperAgent.generate_clarifying_questions(prompt=prompt, skill_preset=skill_preset)
        plan = SuperAgent.decompose_idea(
            prompt=prompt,
            target_aspect_ratio=aspect_ratio,
            character=character,
            skill_preset=skill_preset,
            clarifying_answers=clarifying_answers,
        )
        wallet = CreditService.get_or_create_wallet(request.user)
        AgentSafetyValidator.validate_plan(plan, wallet, strict_balance=False)

        # Persist or update AgentConversation thread
        conv = None
        if conversation_id:
            conv = AgentConversation.objects.filter(id=conversation_id, user=request.user).first()
        if not conv:
            conv = AgentConversation.objects.create(
                user=request.user,
                title=plan.project_title[:150],
                skill_preset=skill_preset,
                aspect_ratio=aspect_ratio,
                character=character,
                clarifying_questions=clarifying_questions,
                clarifying_answers=clarifying_answers,
                plan_snapshot=json.loads(plan.model_dump_json()),
                status='planned',
            )
        else:
            conv.skill_preset = skill_preset
            conv.aspect_ratio = aspect_ratio
            conv.character = character
            conv.clarifying_answers = clarifying_answers
            conv.plan_snapshot = json.loads(plan.model_dump_json())
            conv.status = 'planned'
            conv.save()

        AgentMessage.objects.create(
            conversation=conv,
            role='user',
            content=prompt,
            metadata={'skill_preset': skill_preset, 'clarifying_answers': clarifying_answers},
        )
        AgentMessage.objects.create(
            conversation=conv,
            role='assistant',
            content=f"Synthesized {len(plan.scenes)}-scene storyboard '{plan.project_title}' ({plan.estimated_total_duration}s, {plan.estimated_total_credits} cr).",
            metadata={'scene_count': len(plan.scenes), 'estimated_credits': plan.estimated_total_credits},
        )
    except Exception as exc:
        return HttpResponse(f"<div class='p-4 bg-rose-500/20 border border-rose-500/30 text-rose-300 rounded-2xl text-sm flex items-center justify-between'><span>⚠️ {exc}</span></div>")

    # Return structured storyboard review card
    return render(request, 'partials/agent_plan_card.html', {
        'plan': plan,
        'plan_json': plan.model_dump_json(),
        'wallet': wallet,
        'has_sufficient_balance': wallet.balance >= plan.estimated_total_credits,
        'conversation': conv,
        'clarifying_questions': clarifying_questions,
        'clarifying_answers': clarifying_answers,
        'prompt': prompt,
        'skill_preset': skill_preset,
    })

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

            conversation_id = request.POST.get('conversation_id', '').strip()
            if conversation_id:
                conv = AgentConversation.objects.filter(id=conversation_id, user=request.user).first()
                if conv:
                    conv.project = project
                    conv.plan_snapshot = json.loads(plan.model_dump_json())
                    conv.status = 'executed'
                    conv.save(update_fields=['project', 'plan_snapshot', 'status', 'updated_at'])

        # 4. Dispatch Celery tasks only after transaction successfully commits
        for gen_id in dispatched_gen_ids:
            dispatch_generation_task.delay(gen_id)

        return redirect('projects:detail', pk=project.pk)

    except Exception as exc:
        return HttpResponse(f"<div class='p-3 bg-rose-500/20 text-rose-300 rounded-lg'>{exc}</div>", status=400)


@login_required
def load_agent_conversation_view(request, conversation_id):
    """Loads a saved AgentConversation's storyboard plan into the interactive review card."""
    conv = get_object_or_404(AgentConversation, id=conversation_id, user=request.user)
    if not conv.plan_snapshot:
        return HttpResponse("<div class='p-4 bg-amber-500/20 border border-amber-500/30 text-amber-300 rounded-2xl text-sm'>No storyboard snapshot stored for this conversation.</div>")

    plan = StoryboardPlan(**conv.plan_snapshot)
    wallet = CreditService.get_or_create_wallet(request.user)
    first_user_msg = conv.messages.filter(role='user').order_by('created_at').first()
    prompt_text = first_user_msg.content if first_user_msg else conv.title

    return render(request, 'partials/agent_plan_card.html', {
        'plan': plan,
        'plan_json': plan.model_dump_json(),
        'wallet': wallet,
        'has_sufficient_balance': wallet.balance >= plan.estimated_total_credits,
        'conversation': conv,
        'clarifying_questions': conv.clarifying_questions or [],
        'clarifying_answers': conv.clarifying_answers or {},
        'prompt': prompt_text,
        'skill_preset': conv.skill_preset,
    })


@login_required
@require_POST
def apply_viral_effect_view(request, slug):
    """One-Tap Viral Video Effect launcher: injects subject/character into curated VFX template and queues generation."""
    ViralEffectTemplate.ensure_seeded()
    effect = get_object_or_404(ViralEffectTemplate, slug=slug, is_active=True)
    subject = request.POST.get('subject', '').strip()
    character_id = request.POST.get('character_id', '').strip()

    character = None
    if character_id:
        character = Character.objects.filter(id=character_id, owner=request.user).first()
        if character and not subject:
            subject = f"{character.name} ({character.appearance_description})"

    rendered_prompt = effect.render_prompt(subject or "a heroic subject")

    try:
        model = ModelRouter.select_model(
            modality='video',
            user_preference='automatic',
            duration=effect.duration,
            aspect_ratio=effect.aspect_ratio,
        )
        cost = model.calculate_credit_cost(effect.duration)
        with transaction.atomic():
            gen = Generation.objects.create(
                user=request.user,
                character=character,
                generation_type='video',
                provider=model.provider,
                model=model,
                model_id_snapshot=model.model_id,
                prompt=rendered_prompt,
                duration=effect.duration,
                aspect_ratio=effect.aspect_ratio,
                status='queued',
                provider_response={'viral_effect': effect.slug, 'effect_name': effect.name},
            )
            CreditService.reserve_credits(request.user, cost, gen)
        dispatch_generation_task.delay(str(gen.id))
        messages.success(request, f"Launched One-Tap Viral Effect '{effect.name}' ({cost} credits reserved).")
        return redirect('generations:history')
    except Exception as exc:
        messages.error(request, f"Could not launch effect: {exc}")
        return redirect('agent:studio')

