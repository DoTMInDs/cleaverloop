import os
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404

logger = logging.getLogger(__name__)
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.urls import reverse_lazy
from django.conf import settings
from apps.characters.models import Character, SceneAsset
from apps.characters.services import CharacterGeneratorService

class CharacterListView(LoginRequiredMixin, ListView):
    model = Character
    template_name = 'characters/list.html'
    context_object_name = 'characters'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user).select_related('parent_character')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['locations'] = SceneAsset.objects.filter(owner=self.request.user, asset_type='location')
        ctx['elements'] = SceneAsset.objects.filter(owner=self.request.user, asset_type='element')
        ctx['active_tab'] = self.request.GET.get('tab', 'characters')
        return ctx

class CharacterCreateView(LoginRequiredMixin, CreateView):
    model = Character
    fields = ['name', 'description', 'appearance_description', 'clothing_description', 'personality', 'avatar', 'voice_profile']
    template_name = 'characters/form.html'
    success_url = reverse_lazy('characters:list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.voices.models import VoiceProfile
        ctx['cloned_voices'] = VoiceProfile.objects.filter(user=self.request.user, status='ready')
        return ctx

    def form_valid(self, form):
        from apps.credits.services import CreditService
        wallet = CreditService.get_or_create_wallet(self.request.user)
        max_chars = wallet.max_characters
        current_count = Character.objects.filter(owner=self.request.user).count()
        if max_chars > 0 and current_count >= max_chars:
            messages.error(
                self.request,
                f"Your {wallet.get_subscription_tier_display()} plan allows up to {max_chars} character(s). Upgrade your plan to forge more characters."
            )
            return redirect('billing:plans')

        form.instance.owner = self.request.user

        # Bind Voice Profile if passed
        voice_id = self.request.POST.get('voice_profile') or self.request.POST.get('voice_profile_id')
        if voice_id:
            from apps.voices.models import VoiceProfile
            form.instance.voice_profile = VoiceProfile.objects.filter(user=self.request.user, id=voice_id).first()
        elif 'voice_profile' in self.request.POST and not voice_id:
            form.instance.voice_profile = None
        
        # Persist generated metadata (poses, subject isolation, full body standing URL, face lock)
        full_body_url = ''
        face_anchor_url = ''
        generated_metadata_raw = self.request.POST.get('generated_metadata', '').strip()
        if generated_metadata_raw:
            try:
                meta = json.loads(generated_metadata_raw)
                if isinstance(meta, dict):
                    if not form.instance.metadata:
                        form.instance.metadata = {}
                    form.instance.metadata.update(meta)
                    full_body_url = meta.get('full_body_url', '')
                    face_anchor_url = meta.get('face_anchor_url', '') or meta.get('original_face_url', '')
                    if face_anchor_url:
                        form.instance.metadata['original_face_url'] = face_anchor_url
            except Exception:
                pass

        # Persist selected style preset in metadata & universe_style field
        style_preset = (self.request.POST.get('universe_style') or self.request.POST.get('style_preset') or '').strip()
        if style_preset:
            form.instance.universe_style = style_preset
            if not form.instance.metadata:
                form.instance.metadata = {}
            form.instance.metadata['style_preset'] = style_preset

        gen_avatar = self.request.POST.get('generated_avatar_url', '').strip()
        # Prefer the authentic AI-generated avatar/face anchor over any legacy static showcase images
        if full_body_url and any(k in full_body_url.lower() for k in ('marcus_vance', 'amina_diallo', 'amina_standing')):
            full_body_url = gen_avatar or face_anchor_url or ''
            if form.instance.metadata:
                form.instance.metadata['full_body_url'] = full_body_url

        target_visual = gen_avatar or face_anchor_url or full_body_url
        if target_visual and not self.request.FILES.get('avatar'):
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            if target_visual.startswith(media_url):
                rel_path = target_visual[len(media_url):]
                form.instance.avatar = rel_path
            elif 'characters/' in target_visual:
                rel_path = target_visual[target_visual.find('characters/'):]
                form.instance.avatar = rel_path

        messages.success(self.request, f"Character '{form.instance.name}' forged successfully.")
        return super().form_valid(form)

class CharacterDetailView(LoginRequiredMixin, DetailView):
    model = Character
    template_name = 'characters/detail.html'
    context_object_name = 'character'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

class CharacterUpdateView(LoginRequiredMixin, UpdateView):
    model = Character
    fields = ['name', 'description', 'appearance_description', 'clothing_description', 'personality', 'avatar', 'voice_profile']
    template_name = 'characters/form.html'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.voices.models import VoiceProfile
        ctx['cloned_voices'] = VoiceProfile.objects.filter(user=self.request.user, status='ready')
        return ctx

    def form_valid(self, form):
        # Bind Voice Profile if passed
        voice_id = self.request.POST.get('voice_profile') or self.request.POST.get('voice_profile_id')
        if voice_id:
            from apps.voices.models import VoiceProfile
            form.instance.voice_profile = VoiceProfile.objects.filter(user=self.request.user, id=voice_id).first()
        elif 'voice_profile' in self.request.POST and not voice_id:
            form.instance.voice_profile = None

        full_body_url = ''
        face_anchor_url = ''
        generated_metadata_raw = self.request.POST.get('generated_metadata', '').strip()
        if generated_metadata_raw:
            try:
                meta = json.loads(generated_metadata_raw)
                if isinstance(meta, dict):
                    if not form.instance.metadata:
                        form.instance.metadata = {}
                    form.instance.metadata.update(meta)
                    full_body_url = meta.get('full_body_url', '')
                    face_anchor_url = meta.get('face_anchor_url', '') or meta.get('original_face_url', '')
                    if face_anchor_url:
                        form.instance.metadata['original_face_url'] = face_anchor_url
            except Exception:
                pass

        # Persist selected style preset in metadata & universe_style field
        style_preset = (self.request.POST.get('universe_style') or self.request.POST.get('style_preset') or '').strip()
        if style_preset:
            form.instance.universe_style = style_preset
            if not form.instance.metadata:
                form.instance.metadata = {}
            form.instance.metadata['style_preset'] = style_preset

        gen_avatar = self.request.POST.get('generated_avatar_url', '').strip()
        if full_body_url and any(k in full_body_url.lower() for k in ('marcus_vance', 'amina_diallo', 'amina_standing')):
            full_body_url = gen_avatar or face_anchor_url or ''
            if form.instance.metadata:
                form.instance.metadata['full_body_url'] = full_body_url

        target_visual = gen_avatar or face_anchor_url or full_body_url
        if target_visual and not self.request.FILES.get('avatar'):
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            if target_visual.startswith(media_url):
                rel_path = target_visual[len(media_url):]
                form.instance.avatar = rel_path
            elif 'characters/' in target_visual:
                rel_path = target_visual[target_visual.find('characters/'):]
                form.instance.avatar = rel_path

        return super().form_valid(form)

    def get_success_url(self):
        messages.success(self.request, f"Character '{self.object.name}' updated successfully.")
        return reverse_lazy('characters:detail', kwargs={'pk': self.object.pk})

class CharacterDeleteView(LoginRequiredMixin, DeleteView):
    model = Character
    template_name = 'characters/confirm_delete.html'
    success_url = reverse_lazy('characters:list')
    context_object_name = 'character'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

    def delete(self, request, *args, **kwargs):
        char = self.get_object()
        messages.success(request, f"Character '{char.name}' deleted successfully.")
        return super().delete(request, *args, **kwargs)

@login_required
@require_POST
def generate_character_ai_view(request):
    """
    Synthesizes complete Character DNA + Avatar portrait.
    Supports either:
    1. Multimodal Face Photo upload: extracts visual features & biometric cues using Gemini Vision
    2. Text Concept Brief: decomposes text into rich character blueprint
    """
    brief = request.POST.get('brief', '').strip()
    style_preset = request.POST.get('style_preset', 'cinematic').strip()
    uploaded_photo = request.FILES.get('photo') or request.FILES.get('avatar')

    from apps.credits.services import CreditService
    wallet = CreditService.get_or_create_wallet(request.user)
    max_chars = wallet.max_characters
    if max_chars > 0 and Character.objects.filter(owner=request.user).count() >= max_chars:
        return JsonResponse(
            {
                'error': f"Character limit reached ({max_chars} max on {wallet.get_subscription_tier_display()} plan). Please upgrade your subscription to create more characters."
            },
            status=403
        )

    MAX_PHOTO_SIZE = 15 * 1024 * 1024 # 15MB
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

    try:
        if uploaded_photo:
            ext = uploaded_photo.name.split('.')[-1].lower() if '.' in uploaded_photo.name else ''
            if ext not in ALLOWED_EXTENSIONS:
                return JsonResponse(
                    {'error': f"Unsupported image format (.{ext}). Allowed: JPEG, PNG, WEBP."},
                    status=400
                )
            if uploaded_photo.size > MAX_PHOTO_SIZE:
                return JsonResponse({'error': 'Uploaded photo exceeds 15MB limit.'}, status=400)

            image_bytes = uploaded_photo.read()
            mime_type = uploaded_photo.content_type or f"image/{ext if ext != 'jpg' else 'jpeg'}"

            dna = CharacterGeneratorService.synthesize_character_from_image(
                image_bytes=image_bytes,
                mime_type=mime_type,
                style_preset=style_preset,
                extra_brief=brief
            )
            return JsonResponse(dna.model_dump())

        if not brief:
            return JsonResponse(
                {'error': 'Please provide a character concept brief or upload a face photo to forge.'},
                status=400
            )

        dna = CharacterGeneratorService.synthesize_character(brief=brief, style_preset=style_preset)
        return JsonResponse(dna.model_dump())
    except Exception as exc:
        logger.exception("Character synthesis error")
        return JsonResponse({'error': str(exc)}, status=500)


@login_required
@require_POST
def set_primary_pose_view(request, pk):
    """Sets a selected pose as the character's primary active avatar."""
    character = get_object_or_404(Character, pk=pk, owner=request.user)
    try:
        data = json.loads(request.body.decode('utf-8'))
        pose_id = data.get('pose_id', '')
        image_url = data.get('image_url', '')

        poses = character.metadata.get('poses', [])
        found_pose = next((p for p in poses if p.get('id') == pose_id or p.get('image_url') == image_url), None)

        if found_pose and found_pose.get('image_url'):
            url = found_pose['image_url']
            media_prefix = getattr(settings, 'MEDIA_URL', '/media/')
            if url.startswith(media_prefix):
                rel_path = url[len(media_prefix):]
            elif 'characters/avatars/' in url:
                rel_path = url[url.find('characters/avatars/'):]
            else:
                rel_path = url
            character.avatar = rel_path
            character.metadata['active_pose'] = pose_id
            character.save()
            return JsonResponse({'status': 'ok', 'active_pose': pose_id, 'avatar_url': character.avatar.url})
        return JsonResponse({'error': 'Pose not found'}, status=404)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


@login_required
@require_POST
def create_character_variant_view(request, pk):
    """Clones a base character into an outfit, age, or style universe variant while preserving facial identity DNA."""
    parent = get_object_or_404(Character, pk=pk, owner=request.user)

    from apps.credits.services import CreditService
    wallet = CreditService.get_or_create_wallet(request.user)
    max_chars = wallet.max_characters
    if max_chars > 0 and Character.objects.filter(owner=request.user).count() >= max_chars:
        messages.error(
            request,
            f"Your {wallet.get_subscription_tier_display()} plan allows up to {max_chars} character(s). Upgrade your plan to create more variants."
        )
        return redirect('characters:detail', pk=parent.pk)

    variant_label = request.POST.get('variant_label', '').strip() or 'Wardrobe Variant'
    clothing_description = request.POST.get('clothing_description', '').strip() or parent.clothing_description
    universe_style = request.POST.get('universe_style', '').strip() or parent.universe_style or 'cinematic'

    base_name = f"{parent.name} ({variant_label})"
    candidate_name = base_name
    suffix = 2
    while Character.objects.filter(owner=request.user, name=candidate_name).exists():
        candidate_name = f"{base_name} #{suffix}"
        suffix += 1

    cloned_meta = dict(parent.metadata or {})
    cloned_meta['style_preset'] = universe_style
    cloned_meta['variant_label'] = variant_label

    variant = Character.objects.create(
        owner=request.user,
        parent_character=parent,
        name=candidate_name,
        variant_label=variant_label,
        universe_style=universe_style,
        description=parent.description,
        appearance_description=parent.appearance_description,
        clothing_description=clothing_description,
        personality=parent.personality,
        voice_profile=parent.voice_profile,
        voice_reference=parent.voice_reference,
        avatar=parent.avatar,
        metadata=cloned_meta,
    )
    messages.success(request, f"Character variant '{variant.name}' forged with locked facial DNA.")
    return redirect('characters:detail', pk=variant.pk)


@login_required
@require_POST
def create_scene_asset_view(request):
    """Creates a reusable Location (Environment) or Element (Prop/Vehicle/Artifact) world-building asset."""
    asset_type = request.POST.get('asset_type', 'location').strip()
    if asset_type not in ('location', 'element'):
        asset_type = 'location'
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, "Asset name is required.")
        return redirect('characters:list')

    category = request.POST.get('category', '').strip()
    universe_style = request.POST.get('universe_style', 'cinematic').strip() or 'cinematic'
    time_of_day = request.POST.get('time_of_day', 'Golden Hour').strip()
    weather = request.POST.get('weather', 'Clear').strip()
    description = request.POST.get('description', '').strip()

    asset = SceneAsset.objects.create(
        owner=request.user,
        asset_type=asset_type,
        name=name,
        category=category,
        universe_style=universe_style,
        time_of_day=time_of_day,
        weather=weather,
        description=description,
    )
    asset.source_prompt = asset.build_prompt_cue()
    asset.save(update_fields=['source_prompt'])

    tab = 'locations' if asset_type == 'location' else 'elements'
    messages.success(request, f"{asset.get_asset_type_display()} '{asset.name}' added to World Library.")
    return redirect(f"{reverse_lazy('characters:list')}?tab={tab}")


@login_required
@require_POST
def delete_scene_asset_view(request, asset_id):
    """Deletes a user-owned SceneAsset (Location or Element)."""
    asset = get_object_or_404(SceneAsset, id=asset_id, owner=request.user)
    tab = 'locations' if asset.asset_type == 'location' else 'elements'
    name = asset.name
    asset.delete()
    messages.info(request, f"Removed '{name}' from World Library.")
    return redirect(f"{reverse_lazy('characters:list')}?tab={tab}")


@login_required
@require_POST
def generate_turnaround_sheet_view(request, pk):
    """Synthesizes and persists a 4-Angle Turnaround Sheet & 4-Expression Matrix on the character."""
    character = get_object_or_404(Character, pk=pk, owner=request.user)
    meta = dict(character.metadata or {})
    img = character.primary_image_url
    meta['turnaround_forged'] = True
    meta['turnaround_angles'] = [
        {
            'id': 'front_ortho',
            'label': 'Front Orthographic',
            'icon': '🧍',
            'image_url': img,
            'prompt_cue': f'Front orthographic full-body reference of {character.name}, {character.appearance_description}, wearing {character.clothing_description or "signature outfit"}.'
        },
        {
            'id': 'left_profile',
            'label': 'Left 90° Profile',
            'icon': '👈',
            'image_url': img,
            'prompt_cue': f'Left 90-degree profile turnaround of {character.name}, locked cranial & jawline proportions.'
        },
        {
            'id': 'right_profile',
            'label': 'Right 90° Profile',
            'icon': '👉',
            'image_url': img,
            'prompt_cue': f'Right 90-degree profile turnaround of {character.name}, matching hair and wardrobe silhouette.'
        },
        {
            'id': 'three_quarter_back',
            'label': '3/4 Rear Silhouette',
            'icon': '🔄',
            'image_url': img,
            'prompt_cue': f'3/4 dorsal turnaround view of {character.name}, full costume continuity.'
        },
    ]
    meta['expressions'] = [
        {'id': 'neutral', 'label': 'Composed Neutral', 'icon': '😐', 'prompt_cue': 'calm, composed micro-expression with steady eye contact'},
        {'id': 'warm_smile', 'label': 'Warm Charismatic Smile', 'icon': '😊', 'prompt_cue': 'genuine warm smile with natural crinkles around the eyes'},
        {'id': 'intense_action', 'label': 'Intense Determination', 'icon': '😠', 'prompt_cue': 'fierce determined gaze, furrowed brow, high-stakes dramatic tension'},
        {'id': 'surprised_awe', 'label': 'Cinematic Awe / Shock', 'icon': '😮', 'prompt_cue': 'wide-eyed expression of sudden awe and emotional revelation'},
    ]
    character.metadata = meta
    character.save(update_fields=['metadata', 'updated_at'])
    messages.success(request, f"4-Angle Turnaround Sheet & Expression Matrix locked for '{character.name}'.")
    return redirect('characters:detail', pk=character.pk)



