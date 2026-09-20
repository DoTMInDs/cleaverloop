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
        ctx['wallet'] = getattr(self.request, '_cached_wallet', None) or getattr(user, 'wallet', None) or CreditService.get_or_create_wallet(user)
        ctx['recent_generations'] = Generation.objects.filter(user=user).select_related('output_media', 'model', 'provider')[:8]
        ctx['projects'] = list(Project.objects.filter(owner=user)[:6])
        ctx['projects_count'] = Project.objects.filter(owner=user).count()
        ctx['characters'] = list(Character.objects.filter(owner=user)[:4])
        ctx['characters_count'] = Character.objects.filter(owner=user).count()
        return ctx

class CreateStudioView(LoginRequiredMixin, TemplateView):
    template_name = 'studio/create.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['wallet'] = getattr(self.request, '_cached_wallet', None) or getattr(user, 'wallet', None) or CreditService.get_or_create_wallet(user)
        ctx['image_models'] = AIModel.objects.filter(modality='image', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        ctx['video_models'] = AIModel.objects.filter(modality='video', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        ctx['characters'] = Character.objects.filter(owner=user)
        ctx['projects'] = Project.objects.filter(owner=user)
        ctx['recent_generations'] = Generation.objects.filter(user=user).select_related('output_media', 'model', 'provider')[:4]
        ctx['trending_presets'] = [
            {
                'id': 'vintage_cartoon',
                'title': 'Vintage 1930s Cartoon',
                'icon': '🎞️',
                'tag': 'Rubber Hose',
                'type': 'video',
                'aspect': '16:9',
                'duration': 5,
                'prompt': 'Rubber hose vintage 1930s monochrome animation of a cheerful character whistling and tap dancing down a cobbled street, bouncy squash and stretch physics, authentic film grain, classic cartoon score aesthetic.',
            },
            {
                'id': 'cyberpunk_skeleton',
                'title': 'Neon Hologram Skeleton',
                'icon': '⚡',
                'tag': 'Viral VFX',
                'type': 'video',
                'aspect': '9:16',
                'duration': 5,
                'prompt': 'Glowing electric cyan and neon amber holographic skeleton performing an energetic viral dance in a dark futuristic Tokyo alley, wet rain puddle reflections, cinematic 8k photorealistic.',
            },
            {
                'id': 'claymation_cozy',
                'title': 'Cozy Stop-Motion Clay',
                'icon': '🧸',
                'tag': 'Tactile Stop-Mo',
                'type': 'video',
                'aspect': '16:9',
                'duration': 5,
                'prompt': 'Tactile claymation miniature couple sitting on cozy sofa inside a warm apartment with rain pattering on the window, tactile fingerprint textures, warm 35mm stop-motion lighting.',
            },
            {
                'id': 'fruit_island',
                'title': 'Fruit Island Drama',
                'icon': '🌴',
                'tag': '3D Animation',
                'type': 'video',
                'aspect': '9:16',
                'duration': 5,
                'prompt': 'Animated anthropomorphic pineapple wearing sunglasses arguing dramatically with a blushing cute strawberry on a sunny tropical beach, reality TV confessional camera, Pixar 3D render.',
            },
            {
                'id': 'unhinged_cartoon',
                'title': 'Unhinged Cartoon Motion',
                'icon': '💥',
                'tag': 'Social Viral',
                'type': 'video',
                'aspect': '1:1',
                'duration': 5,
                'prompt': 'Hyperactive wacky 90s animated creature with swirling eyes popping out of a chrome toaster with dynamic comic sparks, exaggerated squash and stretch, vivid saturated colors.',
            },
            {
                'id': 'cinematic_portrait',
                'title': 'Cinematic Neon Portrait',
                'icon': '📸',
                'tag': 'Photoreal Image',
                'type': 'image',
                'aspect': '1:1',
                'duration': 0,
                'prompt': 'Close-up cinematic editorial portrait of an intrepid explorer in a neon-lit cyberpunk market, raindrops on jacket, shallow depth of field, anamorphic bokeh, 8k masterpiece.',
            },
        ]
        return ctx
