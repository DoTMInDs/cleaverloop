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
from apps.characters.models import Character
from apps.characters.services import CharacterGeneratorService

class CharacterListView(LoginRequiredMixin, ListView):
    model = Character
    template_name = 'characters/list.html'
    context_object_name = 'characters'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

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

        # Persist selected style preset in metadata
        style_preset = self.request.POST.get('style_preset', '').strip()
        if style_preset:
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

        # Persist selected style preset in metadata
        style_preset = self.request.POST.get('style_preset', '').strip()
        if style_preset:
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

