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
    fields = ['name', 'description', 'appearance_description', 'clothing_description', 'personality', 'avatar']
    template_name = 'characters/form.html'
    success_url = reverse_lazy('characters:list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        # Check if AI avatar URL was generated and no file was uploaded
        generated_avatar = self.request.POST.get('generated_avatar_url', '').strip()
        if generated_avatar and not self.request.FILES.get('avatar'):
            # Extract relative media path e.g. 'characters/avatars/ai_...'
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            if generated_avatar.startswith(media_url):
                rel_path = generated_avatar[len(media_url):]
                form.instance.avatar = rel_path
            elif 'characters/avatars/' in generated_avatar:
                rel_path = generated_avatar[generated_avatar.find('characters/avatars/'):]
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
    fields = ['name', 'description', 'appearance_description', 'clothing_description', 'personality', 'avatar']
    template_name = 'characters/form.html'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

    def form_valid(self, form):
        generated_avatar = self.request.POST.get('generated_avatar_url', '').strip()
        if generated_avatar and not self.request.FILES.get('avatar'):
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            if generated_avatar.startswith(media_url):
                rel_path = generated_avatar[len(media_url):]
                form.instance.avatar = rel_path
            elif 'characters/avatars/' in generated_avatar:
                rel_path = generated_avatar[generated_avatar.find('characters/avatars/'):]
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
