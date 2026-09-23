import logging
import uuid
import httpx
from typing import Optional, Dict, Any
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from apps.providers.base import (
    BaseAIProvider,
    GenerationRequest,
    ProviderJobResult,
    CostEstimate
)

logger = logging.getLogger(__name__)

# Standard ElevenLabs Pre-made Voice IDs & Metadata Matrix
ELEVENLABS_VOICES = {
    'adam': 'pNInz6obpgDQGcFmaJgB',      # Deep, authoritative narrator
    'rachel': '21m00Tcm4TlvDq8ikWAM',    # Calm, warm female
    'nicole': 'piTKgcLEGmPE4e6mEKli',    # Energetic, crisp narrator
    'antoni': 'ErXwobaYiN019PkySvjV',    # Cinematic storytelling
    'george': 'JBFqnCBsd6RMkjVDRZzb',    # British classic accent
    'bella': 'EXAVITQu4vr4xnSDxMaL',     # Expressive, lively female
    'arnold': 'VR6AewLTigWG4xSOukaG',    # Heroic, commanding
    'josh': 'TxGEqnHWrfWFTfGW9XjX',      # Casual, friendly male
    'domi': 'AZnzlk1XvdvUeBnXmlld',      # Emphatic female
    'sam': 'yoZ06aMxZJJ28mfd3POQ',       # Dynamic voiceover
}

VOICE_METADATA = [
    {'id': 'adam', 'name': 'Adam', 'gender': 'Male', 'desc': 'Deep, Cinematic Male Narrator', 'badge': 'Cinematic'},
    {'id': 'rachel', 'name': 'Rachel', 'gender': 'Female', 'desc': 'Warm, Calm Female Voice', 'badge': 'Warm'},
    {'id': 'nicole', 'name': 'Nicole', 'gender': 'Female', 'desc': 'Energetic, Crisp Female Narrator', 'badge': 'Lively'},
    {'id': 'antoni', 'name': 'Antoni', 'gender': 'Male', 'desc': 'Natural, Engaging Male Storyteller', 'badge': 'Engaging'},
    {'id': 'george', 'name': 'George', 'gender': 'Male', 'desc': 'British Classic Accent', 'badge': 'British'},
    {'id': 'bella', 'name': 'Bella', 'gender': 'Female', 'desc': 'Expressive, Emotional Female Voice', 'badge': 'Expressive'},
    {'id': 'josh', 'name': 'Josh', 'gender': 'Male', 'desc': 'Casual, Everyday Relatable Male', 'badge': 'Conversational'},
    {'id': 'arnold', 'name': 'Arnold', 'gender': 'Male', 'desc': 'Commanding, Heroic Male Persona', 'badge': 'Authoritative'},
    {'id': 'sam', 'name': 'Sam', 'gender': 'Male', 'desc': 'Dynamic, Confident Commercial Voice', 'badge': 'Dynamic'},
]

class ElevenLabsProvider(BaseAIProvider):
    """
    Dedicated Adapter for ElevenLabs Neural Audio & Speech Generation.
    Supports Multilingual V2 TTS, Turbo V2.5, and Sound Effects & Foley.
    Seamlessly falls back to Fal.ai Kokoro/MMAudio or Mock if direct key is absent.
    """
    provider_slug = "elevenlabs"
    BASE_URL = "https://api.elevenlabs.io/v1"

    @classmethod
    def get_available_voices(cls, user=None):
        """Return available voice personas dynamically, including user cloned voices."""
        voices = list(VOICE_METADATA)
        if user and user.is_authenticated:
            try:
                from apps.voices.models import VoiceProfile
                cloned = VoiceProfile.objects.filter(user=user, status='ready').order_by('-is_default', '-created_at')
                cloned_meta = []
                for p in cloned:
                    cloned_meta.append({
                        'id': p.provider_voice_id or str(p.id),
                        'name': p.name,
                        'gender': p.get_gender_display(),
                        'desc': p.description or f"{p.accent} Cloned Voice",
                        'badge': 'My Clone',
                        'is_cloned': True,
                        'preview_url': p.preview_url,
                    })
                if cloned_meta:
                    return cloned_meta + voices
            except Exception as e:
                logger.debug(f"Could not load user cloned voices: {e}")
        return voices

    def __init__(self):
        self.api_key = getattr(settings, 'ELEVENLABS_API_KEY', '') or getattr(settings, 'ELEVEN_API_KEY', '')

    def _get_headers(self) -> Dict[str, str]:
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def _save_audio_bytes(self, audio_bytes: bytes, ext: str = "mp3") -> str:
        """Save synthesized audio bytes to default storage and return the public URL."""
        filename = f"uploads/{uuid.uuid4().hex[:12]}.{ext}"
        saved_path = default_storage.save(filename, ContentFile(audio_bytes))
        return default_storage.url(saved_path)

    def clone_voice(self, name: str, description: str = "", audio_file_paths: list = None, labels: dict = None) -> str:
        """
        Instant Voice Clone (IVC): Upload 1 or more audio samples to create a custom voice profile.
        """
        if self.api_key and audio_file_paths:
            try:
                import json
                import os
                import mimetypes

                files_payload = []
                open_handles = []
                for path in audio_file_paths:
                    if os.path.exists(path):
                        fh = open(path, "rb")
                        open_handles.append(fh)
                        mime_type, _ = mimetypes.guess_type(path)
                        files_payload.append(
                            ("files", (os.path.basename(path), fh, mime_type or "audio/mpeg"))
                        )

                data_payload = {
                    "name": name,
                    "description": description or f"Cloned voice for {name}",
                }
                if labels:
                    data_payload["labels"] = json.dumps(labels)

                endpoint = f"{self.BASE_URL}/voices/add"
                headers = {"xi-api-key": self.api_key}

                try:
                    with httpx.Client(timeout=60.0) as client:
                        resp = client.post(endpoint, data=data_payload, files=files_payload, headers=headers)
                        if resp.status_code == 200:
                            voice_id = resp.json().get("voice_id")
                            logger.info(f"ElevenLabs Instant Voice Clone succeeded: {voice_id}")
                            return voice_id
                        logger.error(f"ElevenLabs Voice Clone API error ({resp.status_code}): {resp.text}")
                        raise RuntimeError(f"ElevenLabs Voice Clone error: {resp.text[:200]}")
                finally:
                    for fh in open_handles:
                        try:
                            fh.close()
                        except Exception:
                            pass

            except Exception as exc:
                logger.error(f"ElevenLabs voice clone exception: {exc}")
                raise

        # Offline / Mock Fallback
        from apps.providers.adapters.mock_provider import MockAIProvider
        return MockAIProvider().clone_voice(name, description, audio_file_paths, labels)

    def delete_voice(self, voice_id: str) -> bool:
        """Delete cloned voice upstream on ElevenLabs."""
        if self.api_key and voice_id and not voice_id.startswith("mock-"):
            try:
                endpoint = f"{self.BASE_URL}/voices/{voice_id}"
                headers = {"xi-api-key": self.api_key}
                with httpx.Client(timeout=20.0) as client:
                    resp = client.delete(endpoint, headers=headers)
                    return resp.status_code == 200
            except Exception as exc:
                logger.warning(f"Could not delete ElevenLabs voice {voice_id}: {exc}")
        return True

    def generate_audio(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        """
        Generate high-fidelity speech or cinematic sound effects.
        """
        # If native ElevenLabs API key is configured, call ElevenLabs REST API directly
        if self.api_key:
            try:
                # 1. Sound Effects / Foley Generation
                if "sound" in model_id.lower() or "sfx" in model_id.lower() or "foley" in model_id.lower():
                    endpoint = f"{self.BASE_URL}/sound-generation"
                    payload = {
                        "text": request.prompt,
                        "duration_seconds": min(max(float(request.duration or 5), 1.0), 22.0),
                        "prompt_influence": 0.35
                    }
                    with httpx.Client(timeout=45.0) as client:
                        resp = client.post(endpoint, json=payload, headers=self._get_headers())
                        if resp.status_code == 200:
                            media_url = self._save_audio_bytes(resp.content, "mp3")
                            return ProviderJobResult(
                                external_job_id=f"eleven-sfx-{uuid.uuid4().hex[:8]}",
                                status="completed",
                                output_media_url=media_url,
                                raw_response={"provider": "elevenlabs", "type": "sfx"}
                            )
                        logger.warning(f"ElevenLabs SFX API error ({resp.status_code}): {resp.text[:200]}")

                # 2. Text-to-Speech / Character Dialogue
                else:
                    raw_voice = str(request.extra_params.get('voice') or getattr(request, 'voice', 'adam') or 'adam')
                    fallback_canonical = ELEVENLABS_VOICES['adam']
                    
                    # If this is a local VoiceProfile UUID or mock ID, resolve gender/persona
                    try:
                        from apps.voices.models import VoiceProfile
                        from django.db.models import Q
                        voice_profile = VoiceProfile.objects.filter(
                            Q(provider_voice_id=raw_voice) | 
                            (Q(id=raw_voice) if len(raw_voice) == 36 else Q())
                        ).first()
                        if voice_profile:
                            # If this voice profile has real recorded samples from the user, use Fal F5-TTS zero-shot cloning!
                            first_sample = voice_profile.samples.first()
                            if first_sample and first_sample.audio_file and (not voice_profile.provider_voice_id or voice_profile.provider_voice_id.startswith('mock-') or voice_profile.provider == 'fal'):
                                logger.info(f"Voice profile '{voice_profile.name}' has recorded sample; dispatching to Fal F5-TTS neural clone")
                                from apps.providers.adapters.fal_ai import FalAIProvider
                                sample_path = first_sample.audio_file.path if hasattr(first_sample.audio_file, 'path') else first_sample.audio_file.url
                                return FalAIProvider().clone_voice_speech(
                                    text=request.prompt,
                                    ref_audio_path_or_url=sample_path
                                )

                            if voice_profile.gender == 'female':
                                fallback_canonical = ELEVENLABS_VOICES['rachel']
                            elif voice_profile.gender == 'male':
                                fallback_canonical = ELEVENLABS_VOICES['adam']
                            if voice_profile.provider_voice_id and not voice_profile.provider_voice_id.startswith('mock-'):
                                raw_voice = voice_profile.provider_voice_id
                    except Exception as e:
                        logger.debug(f"Could not resolve voice profile: {e}")

                    # Check pre-made voice dictionary first
                    if raw_voice.lower() in ELEVENLABS_VOICES:
                        voice_id = ELEVENLABS_VOICES[raw_voice.lower()]
                    elif raw_voice.startswith('mock-'):
                        voice_id = fallback_canonical
                    elif len(raw_voice) >= 10:
                        voice_id = raw_voice
                    else:
                        voice_id = fallback_canonical
                    
                    eleven_model = "eleven_turbo_v2_5" if "turbo" in model_id.lower() else "eleven_multilingual_v2"
                    endpoint = f"{self.BASE_URL}/text-to-speech/{voice_id}"
                    payload = {
                        "text": request.prompt,
                        "model_id": eleven_model,
                        "voice_settings": {
                            "stability": 0.50,          # Higher stability = more consistent, less robotic (0.0-1.0)
                            "similarity_boost": 0.90,   # How closely to match the voice reference
                            "style": 0.40,              # Emotional style exaggeration
                            "use_speaker_boost": True   # Enhanced speaker clarity
                        },
                        # Optional: Output format for best quality
                        "output_format": "mp3_44100_128"
                    }
                    with httpx.Client(timeout=45.0) as client:
                        resp = client.post(endpoint, json=payload, headers=self._get_headers())
                        # If remote custom voice ID failed (e.g. 400 invalid_uid), retry immediately with canonical voice
                        if resp.status_code == 400 and voice_id != fallback_canonical:
                            logger.warning(
                                f"ElevenLabs rejected custom voice ID '{voice_id}' (400), "
                                f"retrying automatically with high-fidelity canonical voice '{fallback_canonical}'."
                            )
                            fallback_endpoint = f"{self.BASE_URL}/text-to-speech/{fallback_canonical}"
                            resp = client.post(fallback_endpoint, json=payload, headers=self._get_headers())

                        if resp.status_code == 200:
                            media_url = self._save_audio_bytes(resp.content, "mp3")
                            return ProviderJobResult(
                                external_job_id=f"eleven-tts-{uuid.uuid4().hex[:8]}",
                                status="completed",
                                output_media_url=media_url,
                                raw_response={"provider": "elevenlabs", "type": "tts", "voice": raw_voice}
                            )
                        logger.warning(f"ElevenLabs TTS API error ({resp.status_code}): {resp.text[:200]}")

            except Exception as exc:
                logger.error(f"ElevenLabs direct API error: {exc}", exc_info=True)

        # Failover Tier: Use Fal.ai Unified Hub (MMAudio for SFX, Kokoro for Dialogue)
        fal_key = getattr(settings, 'FAL_KEY', '')
        if fal_key:
            from apps.providers.adapters.fal_ai import FalAIProvider
            fal_adapter = FalAIProvider()
            target_fal_model = "fal-mmaudio-v2" if ("sound" in model_id.lower() or "sfx" in model_id.lower() or "foley" in model_id.lower()) else "fal-kokoro"
            return fal_adapter.generate_audio(target_fal_model, request)

        # Mock Safety Net fallback
        from apps.providers.adapters.mock_provider import MockAIProvider
        return MockAIProvider().generate_audio(model_id, request)

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(external_job_id="", status="failed", error_message="Image generation not supported by ElevenLabs.")

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(external_job_id="", status="failed", error_message="Video generation not supported by ElevenLabs.")

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if external_job_id.startswith("fal-ai/"):
            from apps.providers.adapters.fal_ai import FalAIProvider
            return FalAIProvider().get_status(external_job_id)
        return ProviderJobResult(external_job_id=external_job_id, status="completed")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        return CostEstimate(
            estimated_credits=15,
            estimated_duration_sec=int(request.duration or 5),
            provider_cost_cents=1.5
        )

    def health_check(self) -> bool:
        return bool(self.api_key or getattr(settings, 'FAL_KEY', ''))
