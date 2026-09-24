import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.urls import reverse

from apps.voices.models import VoiceProfile, VoiceSample
from apps.voices.services import VoiceCloneService
from apps.credits.services import CreditService
from apps.providers.adapters.elevenlabs import ElevenLabsProvider, VOICE_METADATA
from apps.providers.base import GenerationRequest

logger = logging.getLogger(__name__)

class VoiceListView(LoginRequiredMixin, ListView):
    """Gallery of user's personal cloned voices and standard studio presets."""
    model = VoiceProfile
    template_name = 'voices/list.html'
    context_object_name = 'cloned_voices'

    def get_queryset(self):
        return VoiceProfile.objects.filter(user=self.request.user).prefetch_related('samples')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['preset_voices'] = VOICE_METADATA
        wallet = CreditService.get_or_create_wallet(self.request.user)
        ctx['wallet'] = wallet
        ctx['clone_cost'] = wallet.voice_clone_cost
        ctx['max_voice_profiles'] = wallet.max_voice_profiles
        ctx['can_clone_voices'] = wallet.can_clone_voices
        ctx['voice_generation_cost'] = wallet.voice_generation_cost
        ctx['voice_count'] = VoiceProfile.objects.filter(user=self.request.user).count()
        return ctx

class VoiceCreateView(LoginRequiredMixin, TemplateView):
    """Voice Clone Lab with in-browser mic recorder and audio file uploader."""
    template_name = 'voices/create.html'

    def get(self, request, *args, **kwargs):
        """Redirect direct GET navigations to the voices list page with the create modal open."""
        return redirect(reverse('voices:list') + '?create=1')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        wallet = CreditService.get_or_create_wallet(self.request.user)
        ctx['wallet'] = wallet
        ctx['clone_cost'] = wallet.voice_clone_cost
        ctx['max_voice_profiles'] = wallet.max_voice_profiles
        ctx['can_clone_voices'] = wallet.can_clone_voices
        ctx['voice_generation_cost'] = wallet.voice_generation_cost
        ctx['voice_count'] = VoiceProfile.objects.filter(user=self.request.user).count()
        return ctx

    def post(self, request, *args, **kwargs):
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        gender = request.POST.get('gender', 'neutral').strip()
        accent = request.POST.get('accent', 'Neutral').strip()
        consent = request.POST.get('consent') in ('on', 'true', '1', True)

        if not name:
            messages.error(request, "Please provide a name for your cloned voice persona.")
            return redirect(reverse('voices:list') + '?create=1')

        if not consent:
            messages.error(request, "You must check the confirmation acknowledging legal rights to clone this voice.")
            return redirect(reverse('voices:list') + '?create=1')

        # Collect uploaded samples (from file input or recorded audio blob)
        sample_files = []
        if 'audio_samples' in request.FILES:
            sample_files.extend(request.FILES.getlist('audio_samples'))
        if 'recorded_audio' in request.FILES:
            sample_files.append(request.FILES['recorded_audio'])

        if not sample_files:
            messages.error(request, "Please record or upload at least one audio sample.")
            return redirect(reverse('voices:list') + '?create=1')

        try:
            profile = VoiceCloneService.clone_voice(
                user=request.user,
                name=name,
                description=description,
                gender=gender,
                accent=accent,
                sample_files=sample_files,
                consent_confirmed=True
            )
            messages.success(request, f"Voice '{profile.name}' cloned successfully! Your neural voice profile is ready to use.")
            return redirect('voices:detail', pk=profile.pk)
        except Exception as exc:
            logger.error(f"Voice clone error: {exc}")
            messages.error(request, f"Could not clone voice: {exc}")
            return redirect(reverse('voices:list') + '?create=1')

class VoiceDetailView(LoginRequiredMixin, DetailView):
    """Inspect voice profile, original retained samples, and test dialogue console."""
    model = VoiceProfile
    template_name = 'voices/detail.html'
    context_object_name = 'voice'

    def get_queryset(self):
        return VoiceProfile.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['samples'] = self.object.samples.all()
        ctx['characters'] = self.object.characters.all() if hasattr(self.object, 'characters') else []
        ctx['wallet'] = CreditService.get_or_create_wallet(self.request.user)
        return ctx

class VoiceDeleteView(LoginRequiredMixin, View):
    """Safely delete voice profile locally and upstream."""
    def post(self, request, pk):
        voice = get_object_or_404(VoiceProfile, id=pk, user=request.user)
        name = voice.name
        VoiceCloneService.delete_voice(voice)
        messages.success(request, f"Voice '{name}' has been deleted.")
        return redirect('voices:list')

@login_required
@require_POST
def api_preview_speech(request):
    """Fast AJAX endpoint to synthesize spoken dialogue in a cloned voice with membership-based billing."""
    try:
        text = request.POST.get('text', '').strip()
        voice_id = request.POST.get('voice_id', '').strip()
        voice_profile_id = request.POST.get('voice_profile_id', '').strip()

        if not text:
            return JsonResponse({"error": "Please provide dialogue text to audition."}, status=400)

        # Deduct speech generation credits based on user's membership tier
        ok, cost, msg = CreditService.deduct_voice_generation(request.user, text=text, voice_id=voice_id)
        if not ok:
            return JsonResponse({"error": msg, "insufficient_credits": True}, status=402)

        # Resolve voice ID and profile
        target_voice_id = voice_id
        profile = None
        if voice_profile_id:
            profile = VoiceProfile.objects.filter(id=voice_profile_id, user=request.user).first()
            if profile and profile.provider_voice_id:
                target_voice_id = profile.provider_voice_id

        # If this is a Fal voice or has recorded audio samples, synthesize directly with Fal F5-TTS
        if profile and (profile.provider == 'fal' or profile.samples.exists()):
            first_sample = profile.samples.first()
            if first_sample and first_sample.audio_file:
                from apps.providers.adapters.fal_ai import FalAIProvider
                sample_path = first_sample.audio_file.path if hasattr(first_sample.audio_file, 'path') else first_sample.audio_file.url
                result = FalAIProvider().clone_voice_speech(
                    text=text,
                    ref_audio_path_or_url=sample_path
                )
                if result.status == 'completed' and result.output_media_url:
                    wallet = CreditService.get_or_create_wallet(request.user)
                    return JsonResponse({
                        "status": "success",
                        "audio_url": result.output_media_url,
                        "credits_deducted": cost,
                        "remaining_balance": wallet.balance,
                        "formatted_balance": wallet.formatted_balance
                    })
                # Refund on failure
                if cost > 0:
                    CreditService.grant_credits(
                        request.user,
                        amount=cost,
                        transaction_type='generation_refund',
                        description=f"Refund: Voice synthesis failed ({str(result.error_message)[:40]})"
                    )
                return JsonResponse({"error": result.error_message or "Fal.ai voice synthesis failed"}, status=400)

        if not target_voice_id:
            target_voice_id = 'adam'

        req = GenerationRequest(
            prompt=text,
            duration=max(3, int(len(text.split()) / 2.5)),
            extra_params={'voice': target_voice_id}
        )
        eleven_adapter = ElevenLabsProvider()
        result = eleven_adapter.generate_audio("eleven_multilingual_v2", req)

        if result.status == 'completed' and result.output_media_url:
            wallet = CreditService.get_or_create_wallet(request.user)
            return JsonResponse({
                "status": "success",
                "audio_url": result.output_media_url,
                "credits_deducted": cost,
                "remaining_balance": wallet.balance,
                "formatted_balance": wallet.formatted_balance
            })

        # Refund on failure
        if cost > 0:
            CreditService.grant_credits(
                request.user,
                amount=cost,
                transaction_type='generation_refund',
                description=f"Refund: Voice synthesis failed ({str(result.error_message)[:40]})"
            )
        return JsonResponse({"error": result.error_message or "Synthesis failed"}, status=400)

    except Exception as exc:
        logger.error(f"Speech audition error: {exc}")
        return JsonResponse({"error": str(exc)}, status=500)
