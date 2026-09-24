import logging
import uuid
import os
import sys
from typing import List, Optional
from django.conf import settings
from django.db import transaction
from django.core.files.base import ContentFile
from apps.voices.models import VoiceProfile, VoiceSample
from apps.media.models import Media
from apps.credits.services import CreditService
from apps.providers.adapters.elevenlabs import ElevenLabsProvider
from apps.providers.base import GenerationRequest

logger = logging.getLogger(__name__)

class VoiceCloneService:
    """Orchestrates neural voice cloning, sample retention, and speech synthesis."""

    CLONE_CREDIT_COST = getattr(settings, 'CREDIT_COST_VOICE_CLONE', 50)

    @classmethod
    def clone_voice(
        cls,
        user,
        name: str,
        description: str = "",
        gender: str = "neutral",
        accent: str = "Neutral",
        sample_files: Optional[List] = None,
        consent_confirmed: bool = True
    ) -> VoiceProfile:
        """
        Creates a new neural voice profile, stores original audio samples permanently,
        and synchronizes with ElevenLabs (or Mock engine).
        """
        if not consent_confirmed:
            raise ValueError("You must confirm you have the legal right and consent to clone this voice.")

        if not sample_files or len(sample_files) == 0:
            raise ValueError("Please provide at least one audio sample (recording or file upload) to clone.")

        # Check existing name for this user
        if VoiceProfile.objects.filter(user=user, name__iexact=name.strip()).exists():
            raise ValueError(f"You already have a voice profile named '{name.strip()}'. Please choose a unique name.")

        # Atomic membership quota & credit check
        wallet = CreditService.get_or_create_wallet(user)
        if not wallet.can_clone_voices:
            raise ValueError("Custom neural voice cloning requires a paid subscription (Starter, Creator, or Ultra). Please upgrade your plan.")

        max_voices = wallet.max_voice_profiles
        if max_voices > 0:
            current_count = VoiceProfile.objects.filter(user=user).count()
            if current_count >= max_voices:
                tier_label = wallet.get_subscription_tier_display()
                raise ValueError(
                    f"Voice clone profile quota reached ({current_count}/{max_voices}). "
                    f"Your {tier_label} plan allows up to {max_voices} cloned voices. "
                    "Please upgrade to Creator or Ultra for more voice slots, or delete an existing profile."
                )

        clone_cost = wallet.voice_clone_cost
        effective_cost = 0 if (wallet.is_unlimited_eligible and (clone_cost == 0 or wallet.balance <= 0)) else clone_cost

        if effective_cost > 0 and wallet.balance < effective_cost and not wallet.is_unlimited_eligible:
            raise ValueError(
                f"Insufficient credits. Neural voice cloning requires {effective_cost} credits on your plan "
                f"(Current balance: {wallet.balance:,}). Please top up your wallet or upgrade."
            )

        with transaction.atomic():
            # 1. Deduct credits for voice clone setup (if applicable)
            if effective_cost > 0:
                balance_before = wallet.balance
                wallet.balance -= effective_cost
                wallet.lifetime_spent += effective_cost
                wallet.save(update_fields=['balance', 'lifetime_spent', 'updated_at'])

                from apps.credits.models import CreditTransaction
                CreditTransaction.objects.create(
                    wallet=wallet,
                    amount=-effective_cost,
                    transaction_type='generation_consume',
                    balance_before=balance_before,
                    balance_after=wallet.balance,
                    description=f"Neural Voice Clone setup fee ({effective_cost} cr): '{name.strip()}'"
                )
            else:
                from apps.credits.models import CreditTransaction
                CreditTransaction.objects.create(
                    wallet=wallet,
                    amount=0,
                    transaction_type='generation_consume',
                    balance_before=wallet.balance,
                    balance_after=wallet.balance,
                    description=f"Neural Voice Clone setup (Plan Included): '{name.strip()}'"
                )

            # 2. Create VoiceProfile record
            profile = VoiceProfile.objects.create(
                user=user,
                name=name.strip(),
                description=description.strip(),
                gender=gender,
                accent=accent.strip() or 'Neutral',
                provider='elevenlabs',
                status='processing',
                consent_confirmed=True
            )

            # 3. Permanently store all samples in VoiceSample
            saved_sample_paths = []
            for file_obj in sample_files:
                sample = VoiceSample(
                    voice_profile=profile,
                    audio_file=file_obj,
                    file_size=getattr(file_obj, 'size', 0)
                )
                sample.save()
                if sample.audio_file and hasattr(sample.audio_file, 'path'):
                    saved_sample_paths.append(sample.audio_file.path)

        # 4. Dispatch to ElevenLabs Provider (with Mock fallback for testing/dev environments)
        try:
            labels = {
                "gender": gender,
                "accent": accent,
                "created_by": "CleaverLoop-AI"
            }
            is_testing = 'test' in sys.argv or getattr(settings, 'TESTING', False) or getattr(settings, 'MOCK_AI_PROVIDERS', False)
            if is_testing and not getattr(settings, 'ELEVENLABS_ENABLE_LIVE_TESTS', False):
                from apps.providers.adapters.mock_provider import MockAIProvider
                mock = MockAIProvider()
                remote_voice_id = mock.clone_voice(name=profile.name)
                profile.provider = 'mock'
            else:
                eleven_adapter = ElevenLabsProvider()
                try:
                    remote_voice_id = eleven_adapter.clone_voice(
                        name=profile.name,
                        description=profile.description or f"{profile.accent} {profile.get_gender_display()} Voice",
                        audio_file_paths=saved_sample_paths,
                        labels=labels
                    )
                    profile.provider = 'elevenlabs'
                except Exception as clone_err:
                    logger.info(f"ElevenLabs live cloning unavailable ({clone_err}), activating Fal.ai F5-TTS zero-shot voice cloning for '{profile.name}'")
                    remote_voice_id = f"fal-voice-{profile.id.hex[:12]}"
                    profile.provider = 'fal'

            profile.provider_voice_id = remote_voice_id
            profile.status = 'ready'
            profile.save(update_fields=['provider_voice_id', 'status', 'provider'])

            # 5. Synthesize instant greeting preview clip in the user's real voice (skip in unit tests)
            if not is_testing:
                try:
                    cls.generate_voice_preview(profile)
                except Exception as preview_err:
                    logger.warning(f"Voice preview generation skipped: {preview_err}")

        except Exception as exc:
            logger.error(f"Voice cloning upstream failure for profile {profile.id}: {exc}", exc_info=True)
            profile.status = 'failed'
            profile.error_message = str(exc)
            profile.save(update_fields=['status', 'error_message'])

            # Refund credits on failure if any were deducted
            if effective_cost > 0:
                balance_before = wallet.balance
                wallet.balance += effective_cost
                wallet.lifetime_spent = max(0, wallet.lifetime_spent - effective_cost)
                wallet.save(update_fields=['balance', 'lifetime_spent', 'updated_at'])
                CreditTransaction.objects.create(
                    wallet=wallet,
                    amount=effective_cost,
                    transaction_type='generation_refund',
                    balance_before=balance_before,
                    balance_after=wallet.balance,
                    description=f"Refund: Voice Clone failed for '{profile.name}' ({str(exc)[:60]})"
                )
            raise RuntimeError(f"Voice cloning could not be completed: {exc}")

        return profile

    @classmethod
    def generate_voice_preview(cls, profile: VoiceProfile) -> Optional[Media]:
        """Synthesize a short greeting preview clip using the newly cloned voice."""
        try:
            preview_text = (
                f"Hello! This is {profile.name}'s authentic voice, powered by CleaverLoop AI."
            )
            first_sample = profile.samples.first()
            if first_sample and first_sample.audio_file:
                from apps.providers.adapters.fal_ai import FalAIProvider
                sample_path = first_sample.audio_file.path if hasattr(first_sample.audio_file, 'path') else first_sample.audio_file.url
                result = FalAIProvider().clone_voice_speech(
                    text=preview_text,
                    ref_audio_path_or_url=sample_path
                )
            elif profile.provider == 'mock' or getattr(settings, 'MOCK_AI_PROVIDERS', False):
                from apps.providers.adapters.mock_provider import MockAIProvider
                adapter = MockAIProvider()
                req = GenerationRequest(prompt=preview_text, duration=4, extra_params={'voice': profile.provider_voice_id or str(profile.id)})
                result = adapter.generate_audio("eleven_multilingual_v2", req)
            else:
                adapter = ElevenLabsProvider()
                req = GenerationRequest(prompt=preview_text, duration=4, extra_params={'voice': profile.provider_voice_id or str(profile.id)})
                result = adapter.generate_audio("eleven_multilingual_v2", req)

            if result.status == 'completed' and result.output_media_url:
                media = Media.objects.create(
                    owner=profile.user,
                    media_type='audio',
                    storage_key=result.output_media_url,
                    duration=4.0
                )
                is_testing = 'test' in sys.argv or getattr(settings, 'TESTING', False)
                if not is_testing:
                    try:
                        from apps.providers.base import is_safe_external_url
                        if is_safe_external_url(result.output_media_url):
                            import urllib.request
                            req = urllib.request.Request(result.output_media_url, headers={'User-Agent': 'CleaverLoop-AI/1.0'})
                            with urllib.request.urlopen(req, timeout=10) as resp:
                                media.file.save(f"{str(media.id)[:8]}.wav", ContentFile(resp.read()), save=True)
                        else:
                            logger.warning(f"Blocked preview audio download from unsafe external URL: {result.output_media_url}")
                    except Exception as dl_err:
                        logger.warning(f"Could not locally save preview audio file: {dl_err}")
                else:
                    media.file.save(f"{str(media.id)[:8]}.wav", ContentFile(b"RIFF_MOCK_PREVIEW_AUDIO"), save=True)

                VoiceProfile.objects.filter(id=profile.id).update(preview_audio=media)
                profile.preview_audio = media
                return media
        except Exception as exc:
            logger.warning(f"Could not generate voice preview for {profile.id}: {exc}")
        return None

    @classmethod
    def reclone_voice(cls, profile: VoiceProfile, new_sample_files: Optional[List] = None) -> VoiceProfile:
        """
        Re-clone voice using existing retained VoiceSample records plus any newly provided files.
        """
        if new_sample_files:
            for f in new_sample_files:
                sample = VoiceSample(
                    voice_profile=profile,
                    audio_file=f,
                    file_size=getattr(f, 'size', 0)
                )
                sample.save()

        # Collect all existing sample paths
        all_paths = [s.audio_file.path for s in profile.samples.all() if s.audio_file and os.path.exists(s.audio_file.path)]
        if not all_paths:
            raise ValueError("No sample audio files available for re-cloning.")

        labels = {
            "gender": profile.gender,
            "accent": profile.accent,
            "re_cloned": "true"
        }
        eleven_adapter = ElevenLabsProvider()
        try:
            remote_voice_id = eleven_adapter.clone_voice(
                name=profile.name,
                description=profile.description or f"{profile.accent} Voice",
                audio_file_paths=all_paths,
                labels=labels
            )
            profile.provider = 'elevenlabs'
        except Exception as clone_err:
            logger.info(f"ElevenLabs re-clone unavailable ({clone_err}), activating Fal.ai F5-TTS for '{profile.name}'")
            remote_voice_id = f"fal-voice-{profile.id.hex[:12]}"
            profile.provider = 'fal'

        profile.provider_voice_id = remote_voice_id
        profile.status = 'ready'
        profile.error_message = ''
        profile.save(update_fields=['provider_voice_id', 'status', 'error_message', 'provider'])

        try:
            cls.generate_voice_preview(profile)
        except Exception as preview_err:
            logger.warning(f"Voice preview generation skipped on re-clone: {preview_err}")

        return profile

    @classmethod
    def delete_voice(cls, profile: VoiceProfile) -> bool:
        """Deletes voice locally and deletes remote voice ID upstream."""
        if profile.provider_voice_id:
            try:
                ElevenLabsProvider().delete_voice(profile.provider_voice_id)
            except Exception as e:
                logger.warning(f"Upstream voice delete error: {e}")
        profile.delete()
        return True
