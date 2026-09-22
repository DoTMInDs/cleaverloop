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
    def get_available_voices(cls):
        """Return available voice personas dynamically."""
        return VOICE_METADATA

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
                    voice_key = request.extra_params.get('voice') or getattr(request, 'voice', 'adam') or 'adam'
                    voice_id = ELEVENLABS_VOICES.get(str(voice_key).lower(), ELEVENLABS_VOICES['adam'])
                    
                    eleven_model = "eleven_turbo_v2_5" if "turbo" in model_id.lower() else "eleven_multilingual_v2"
                    endpoint = f"{self.BASE_URL}/text-to-speech/{voice_id}"
                    payload = {
                        "text": request.prompt,
                        "model_id": eleven_model,
                        "voice_settings": {
                            "stability": 0.42,
                            "similarity_boost": 0.85,
                            "style": 0.35,
                            "use_speaker_boost": True
                        }
                    }
                    with httpx.Client(timeout=45.0) as client:
                        resp = client.post(endpoint, json=payload, headers=self._get_headers())
                        if resp.status_code == 200:
                            media_url = self._save_audio_bytes(resp.content, "mp3")
                            return ProviderJobResult(
                                external_job_id=f"eleven-tts-{uuid.uuid4().hex[:8]}",
                                status="completed",
                                output_media_url=media_url,
                                raw_response={"provider": "elevenlabs", "type": "tts", "voice": voice_key}
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
