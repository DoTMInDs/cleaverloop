from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.generations.models import Generation
from apps.projects.models import Project
from apps.providers.models import AIModel
from apps.credits.services import CreditService
from apps.characters.models import Character

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
        ctx['image_models'] = AIModel.objects.filter(modality='image', is_enabled=True, provider__is_enabled=True)
        ctx['video_models'] = AIModel.objects.filter(modality='video', is_enabled=True, provider__is_enabled=True)
        ctx['characters'] = Character.objects.filter(owner=user)
        ctx['projects'] = Project.objects.filter(owner=user)
        return ctx
