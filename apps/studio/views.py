from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.generations.models import Generation
from apps.projects.models import Project
from apps.providers.models import AIModel
from apps.credits.services import CreditService
from apps.characters.models import Character

class HomeView(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['featured_models'] = AIModel.objects.filter(is_enabled=True, provider__is_enabled=True).order_by('-priority')[:6]
        ctx['showcase_styles'] = [
            {
                'title': 'Vintage Cartoon (1930s)',
                'category': 'Animation',
                'badge': 'Trending',
                'desc': 'Rubber hose vintage cartoon animation with nostalgic grain, bouncy movement, and classic animation character design.',
                'image': '/static/images/showcase/old_cartoon.jpg',
                'model': 'Google Veo 3.1 & Seedance',
                'prompt': 'A vintage 1930s monochrome rubber hose cartoon character rowing a wooden boat on gentle waves, whistling cheerfully.'
            },
            {
                'title': 'Unhinged Cartoon',
                'category': 'Viral Social',
                'badge': 'Viral',
                'desc': 'Wild, surreal cartoon energy with exaggerated physics, dynamic squash and stretch, designed for high social media retention.',
                'image': '/static/images/showcase/unhinged_cartoon.jpg',
                'model': 'Kling 2.6 & Fal Wan 2.1',
                'prompt': 'Surreal wacky 90s animated creature with swirling eyes jumping out of toaster with explosive animated comic sparks.'
            },
            {
                'title': 'Cozy Claymation (Everyday Life)',
                'category': 'Stop-Motion',
                'badge': 'Staff Pick',
                'desc': 'Tactile clay stop-motion scenes with warm cinematic lighting, fingerprint textures, and heartfelt miniature atmosphere.',
                'image': '/static/images/showcase/everyday_life.jpg',
                'model': 'Veo 3.1 Cinematic',
                'prompt': 'Cozy claymation couple sitting on couch in dimly lit warm apartment with rain outside, laughing at smartphones.'
            },
            {
                'title': 'Viral Neon Skeleton',
                'category': 'Cyberpunk / VFX',
                'badge': 'Social Trend',
                'desc': 'Glowing neon holographic skeletal dancers synced to upbeat club energy, dominating short-form video discovery pages.',
                'image': '/static/images/showcase/viral_skeleton.jpg',
                'model': 'MiniMax Hailuo Video-01',
                'prompt': 'Cyberpunk neon glowing holographic skeleton performing energetic viral dance in dark futuristic alleyway with rain reflections.'
            },
            {
                'title': 'Fruit Love Island',
                'category': '3D Animation',
                'badge': 'Hit Series',
                'desc': 'Whimsical 3D animated fruits living dramatic reality-TV lives in lush tropical sun-drenched beach environments.',
                'image': '/static/images/showcase/fruit_love_island.jpg',
                'model': 'Flux Ultra + Veo 3.1',
                'prompt': 'Animated anthropomorphic pineapple with sunglasses talking dramatically with cute blushing strawberry on tropical island beach.'
            },
        ]
        return ctx

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'studio/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['wallet'] = CreditService.get_or_create_wallet(user)
        ctx['recent_generations'] = Generation.objects.filter(user=user).select_related('output_media', 'model')[:8]
        ctx['projects'] = Project.objects.filter(owner=user)[:6]
        ctx['characters'] = Character.objects.filter(owner=user)[:4]
        return ctx

class CreateStudioView(LoginRequiredMixin, TemplateView):
    template_name = 'studio/create.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['wallet'] = CreditService.get_or_create_wallet(user)
        ctx['image_models'] = AIModel.objects.filter(modality='image', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        ctx['video_models'] = AIModel.objects.filter(modality='video', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        ctx['characters'] = Character.objects.filter(owner=user)
        ctx['projects'] = Project.objects.filter(owner=user)
        return ctx
