import logging
from typing import Dict, Type, Optional, List
from django.conf import settings
from apps.providers.base import BaseAIProvider
from apps.providers.adapters.mock_provider import MockAIProvider
from apps.providers.adapters.google_veo import GoogleVeoProvider
from apps.providers.adapters.kling import KlingProvider
from apps.providers.adapters.seedance import SeedanceProvider
from apps.providers.adapters.alibaba_wan import AlibabaWanProvider
from apps.providers.adapters.openai_adapter import OpenAIProvider
from apps.providers.adapters.flux import FluxProvider
from apps.providers.adapters.minimax import MiniMaxProvider
from apps.providers.adapters.fal_ai import FalAIProvider
from apps.providers.adapters.elevenlabs import ElevenLabsProvider

logger = logging.getLogger(__name__)

class ModelRegistry:
    """
    Central registry mapping provider slugs to adapter instances.
    Provides dynamic model discovery and capability queries.
    """
    _adapters: Dict[str, BaseAIProvider] = {}

    @classmethod
    def register_defaults(cls):
        """Instantiate and register standard provider adapters."""
        cls._adapters["mock"] = MockAIProvider()
        cls._adapters["google"] = GoogleVeoProvider()
        cls._adapters["kling"] = KlingProvider()
        cls._adapters["seedance"] = SeedanceProvider()
        cls._adapters["wan"] = AlibabaWanProvider()
        cls._adapters["openai"] = OpenAIProvider()
        cls._adapters["flux"] = FluxProvider()
        cls._adapters["minimax"] = MiniMaxProvider()
        cls._adapters["fal"] = FalAIProvider()
        cls._adapters["elevenlabs"] = ElevenLabsProvider()

    @classmethod
    def get_provider_adapter(cls, provider_slug: str) -> BaseAIProvider:
        """Retrieve the adapter instance for a provider slug, falling back to mock if enabled."""
        if not cls._adapters:
            cls.register_defaults()

        # If live provider is requested but mock mode is enforced, use mock provider
        if getattr(settings, 'MOCK_PROVIDERS_ENABLED', True) and provider_slug not in cls._adapters:
            return cls._adapters["mock"]

        adapter = cls._adapters.get(provider_slug)
        if not adapter:
            if getattr(settings, 'MOCK_PROVIDERS_ENABLED', True):
                return cls._adapters["mock"]
            raise ValueError(f"Provider adapter '{provider_slug}' not found.")
        
        # If the adapter requires an API key that is absent, return MockAIProvider
        if not adapter.health_check() and getattr(settings, 'MOCK_PROVIDERS_ENABLED', True):
            return cls._adapters["mock"]

        return adapter

    @classmethod
    def seed_initial_catalog(cls):
        """Seed default providers and models into the database if empty."""
        from apps.providers.models import AIProviderConfig, AIModel

        defaults = [
            # Mock Provider
            {
                "provider": {"slug": "mock", "name": "CleaverLoop Mock Studio", "is_enabled": True},
                "models": [
                    {
                        "model_id": "cleaverloop-mock-video",
                        "display_name": "Mock Video Generator (Fast Synthetic)",
                        "modality": "video",
                        "capabilities": ["t2v", "i2v", "audio"],
                        "max_duration": 15,
                        "supported_resolutions": ["720p", "1080p"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "supports_audio": True,
                        "supports_image_reference": True,
                        "credit_cost_fixed": 50,
                        "credit_cost_per_second": 25,
                        "priority": 10,
                    },
                    {
                        "model_id": "cleaverloop-mock-image",
                        "display_name": "Mock Image Generator (Instant)",
                        "modality": "image",
                        "capabilities": ["t2i", "i2i"],
                        "max_duration": 0,
                        "supported_resolutions": ["1024x1024", "1280x720"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1", "4:3"],
                        "supports_image_reference": True,
                        "credit_cost_fixed": 30,
                        "credit_cost_per_second": 0,
                        "priority": 10,
                    },
                    {
                        "model_id": "cleaverloop-mock-audio",
                        "display_name": "Mock Foley & Audio Generator",
                        "modality": "audio",
                        "capabilities": ["audio", "foley", "tts"],
                        "max_duration": 30,
                        "supported_resolutions": [],
                        "supported_aspect_ratios": [],
                        "supports_audio": True,
                        "credit_cost_fixed": 10,
                        "credit_cost_per_second": 2,
                        "priority": 10,
                    }
                ]
            },
            # Google Veo & Imagen
            {
                "provider": {"slug": "google", "name": "Google Gemini & Veo", "is_enabled": True},
                "models": [
                    {
                        "model_id": "veo-3.1-generate-preview",
                        "display_name": "Google Veo 3.1 Cinematic (Premium)",
                        "modality": "video",
                        "capabilities": ["t2v", "i2v", "audio"],
                        "max_duration": 60,
                        "supported_resolutions": ["1080p", "4k"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "supports_audio": True,
                        "supports_image_reference": True,
                        "credit_cost_fixed": 100,
                        "credit_cost_per_second": 75,
                        "priority": 95,
                        "is_premium": True,
                    },
                    {
                        "model_id": "veo-3.1-fast-generate-preview",
                        "display_name": "Google Veo 3.1 Fast",
                        "modality": "video",
                        "capabilities": ["t2v", "i2v"],
                        "max_duration": 30,
                        "supported_resolutions": ["720p", "1080p"],
                        "supported_aspect_ratios": ["16:9", "9:16"],
                        "supports_audio": False,
                        "supports_image_reference": True,
                        "credit_cost_fixed": 60,
                        "credit_cost_per_second": 40,
                        "priority": 85,
                    },
                    {
                        "model_id": "imagen-3.0-generate-002",
                        "display_name": "Google Imagen 3 (Photorealistic)",
                        "modality": "image",
                        "capabilities": ["t2i"],
                        "max_duration": 0,
                        "supported_resolutions": ["1024x1024", "1792x1024"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1", "4:3"],
                        "credit_cost_fixed": 50,
                        "credit_cost_per_second": 0,
                        "priority": 95,
                    }
                ]
            },
            # Kling AI
            {
                "provider": {"slug": "kling", "name": "Kling AI", "is_enabled": True},
                "models": [
                    {
                        "model_id": "kling-v2-6",
                        "display_name": "Kling 2.6 Motion Studio",
                        "modality": "video",
                        "capabilities": ["t2v", "i2v", "character_ref"],
                        "max_duration": 10,
                        "supported_resolutions": ["1080p"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "supports_image_reference": True,
                        "supports_character_reference": True,
                        "credit_cost_fixed": 80,
                        "credit_cost_per_second": 60,
                        "priority": 80,
                    }
                ]
            },
            # Seedance
            {
                "provider": {"slug": "seedance", "name": "ByteDance Seedance", "is_enabled": True},
                "models": [
                    {
                        "model_id": "seedance-2.5",
                        "display_name": "Seedance 2.5 Long-Form & Audio",
                        "modality": "video",
                        "capabilities": ["t2v", "i2v", "audio", "multishot"],
                        "max_duration": 20,
                        "supported_resolutions": ["1080p"],
                        "supported_aspect_ratios": ["16:9", "9:16"],
                        "supports_audio": True,
                        "supports_image_reference": True,
                        "credit_cost_fixed": 75,
                        "credit_cost_per_second": 50,
                        "priority": 78,
                    }
                ]
            },
            # Alibaba Wan
            {
                "provider": {"slug": "wan", "name": "Alibaba Wan", "is_enabled": True},
                "models": [
                    {
                        "model_id": "wan2.1-t2v-14b",
                        "display_name": "Alibaba Wan 2.1 (Budget Video)",
                        "modality": "video",
                        "capabilities": ["t2v"],
                        "max_duration": 10,
                        "supported_resolutions": ["720p"],
                        "supported_aspect_ratios": ["16:9", "9:16"],
                        "credit_cost_fixed": 40,
                        "credit_cost_per_second": 30,
                        "priority": 60,
                    }
                ]
            },
            # OpenAI Image
            {
                "provider": {"slug": "openai", "name": "OpenAI Image", "is_enabled": True},
                "models": [
                    {
                        "model_id": "dall-e-3",
                        "display_name": "GPT Image (DALL-E 3)",
                        "modality": "image",
                        "capabilities": ["t2i"],
                        "max_duration": 0,
                        "supported_resolutions": ["1024x1024", "1792x1024", "1024x1792"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "credit_cost_fixed": 50,
                        "credit_cost_per_second": 0,
                        "priority": 85,
                    }
                ]
            },
            # Flux
            {
                "provider": {"slug": "flux", "name": "Black Forest Labs Flux", "is_enabled": True},
                "models": [
                    {
                        "model_id": "flux-pro-1.1",
                        "display_name": "Flux 1.1 Pro Studio",
                        "modality": "image",
                        "capabilities": ["t2i"],
                        "max_duration": 0,
                        "supported_resolutions": ["1024x1024"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "credit_cost_fixed": 45,
                        "credit_cost_per_second": 0,
                        "priority": 80,
                    }
                ]
            },
            # MiniMax Hailuo AI
            {
                "provider": {"slug": "minimax", "name": "MiniMax Hailuo AI", "is_enabled": True},
                "models": [
                    {
                        "model_id": "minimax-video-01",
                        "display_name": "MiniMax Hailuo Video-01 (Cinematic Physics)",
                        "modality": "video",
                        "capabilities": ["t2v", "i2v"],
                        "max_duration": 10,
                        "supported_resolutions": ["720p", "1080p"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "supports_image_reference": True,
                        "credit_cost_fixed": 75,
                        "credit_cost_per_second": 50,
                        "priority": 92,
                    }
                ]
            },
            # Fal.ai Universal Multi-Model Fallback Hub
            {
                "provider": {"slug": "fal", "name": "Fal.ai Unified Hub", "is_enabled": True},
                "models": [
                    {
                        "model_id": "fal-wan-2.1",
                        "display_name": "Alibaba Wan 2.1 (via Fal.ai)",
                        "modality": "video",
                        "capabilities": ["t2v", "i2v"],
                        "max_duration": 10,
                        "supported_resolutions": ["720p", "1080p"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "supports_image_reference": True,
                        "credit_cost_fixed": 70,
                        "credit_cost_per_second": 40,
                        "priority": 94,
                    },
                    {
                        "model_id": "fal-luma-dream-machine",
                        "display_name": "Luma Dream Machine (via Fal.ai)",
                        "modality": "video",
                        "capabilities": ["t2v", "i2v"],
                        "max_duration": 10,
                        "supported_resolutions": ["720p", "1080p"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "supports_image_reference": True,
                        "credit_cost_fixed": 75,
                        "credit_cost_per_second": 45,
                        "priority": 90,
                    },
                    {
                        "model_id": "fal-cogvideox-5b",
                        "display_name": "CogVideoX-5B (via Fal.ai)",
                        "modality": "video",
                        "capabilities": ["t2v"],
                        "max_duration": 10,
                        "supported_resolutions": ["720p"],
                        "supported_aspect_ratios": ["16:9", "9:16"],
                        "credit_cost_fixed": 50,
                        "credit_cost_per_second": 30,
                        "priority": 75,
                    },
                    {
                        "model_id": "fal-flux-pro",
                        "display_name": "Flux 1.1 Pro Studio (via Fal.ai)",
                        "modality": "image",
                        "capabilities": ["t2i"],
                        "max_duration": 0,
                        "supported_resolutions": ["1024x1024", "1792x1024"],
                        "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "credit_cost_fixed": 45,
                        "credit_cost_per_second": 0,
                        "priority": 82,
                    },
                    {
                        "model_id": "fal-mmaudio-v2",
                        "display_name": "MMAudio Foley & Sound FX (via Fal.ai)",
                        "modality": "audio",
                        "capabilities": ["audio", "foley", "video_to_audio"],
                        "max_duration": 15,
                        "supported_resolutions": [],
                        "supported_aspect_ratios": [],
                        "supports_audio": True,
                        "credit_cost_fixed": 25,
                        "credit_cost_per_second": 5,
                        "priority": 95,
                    },
                    {
                        "model_id": "fal-kokoro",
                        "display_name": "Kokoro Voice & Dialogue TTS (via Fal.ai)",
                        "modality": "audio",
                        "capabilities": ["audio", "tts", "dialogue"],
                        "max_duration": 30,
                        "supported_resolutions": [],
                        "supported_aspect_ratios": [],
                        "supports_audio": True,
                        "credit_cost_fixed": 10,
                        "credit_cost_per_second": 2,
                        "priority": 95,
                    }
                ]
            },
            # ElevenLabs Neural Voice & Audio Hub
            {
                "provider": {"slug": "elevenlabs", "name": "ElevenLabs Studio", "is_enabled": True},
                "models": [
                    {
                        "model_id": "eleven-multilingual-v2",
                        "display_name": "ElevenLabs Multilingual V2 (Cinematic Voice & Dialogue)",
                        "modality": "audio",
                        "capabilities": ["audio", "tts", "dialogue", "voice"],
                        "max_duration": 30,
                        "supported_resolutions": [],
                        "supported_aspect_ratios": [],
                        "supports_audio": True,
                        "credit_cost_fixed": 15,
                        "credit_cost_per_second": 2,
                        "priority": 98,
                        "is_premium": True,
                    },
                    {
                        "model_id": "eleven-turbo-v2",
                        "display_name": "ElevenLabs Flash Turbo (Ultra-Fast Speech)",
                        "modality": "audio",
                        "capabilities": ["audio", "tts", "voice"],
                        "max_duration": 30,
                        "supported_resolutions": [],
                        "supported_aspect_ratios": [],
                        "supports_audio": True,
                        "credit_cost_fixed": 10,
                        "credit_cost_per_second": 1,
                        "priority": 96,
                    },
                    {
                        "model_id": "eleven-sound-effects",
                        "display_name": "ElevenLabs Sound Effects & Foley FX",
                        "modality": "audio",
                        "capabilities": ["audio", "foley", "sfx"],
                        "max_duration": 22,
                        "supported_resolutions": [],
                        "supported_aspect_ratios": [],
                        "supports_audio": True,
                        "credit_cost_fixed": 20,
                        "credit_cost_per_second": 3,
                        "priority": 97,
                    }
                ]
            }
        ]

        for p_data in defaults:
            prov_cfg = p_data["provider"]
            provider, _ = AIProviderConfig.objects.get_or_create(
                slug=prov_cfg["slug"],
                defaults=prov_cfg
            )
            for m_cfg in p_data["models"]:
                AIModel.objects.update_or_create(
                    model_id=m_cfg["model_id"],
                    defaults={**m_cfg, "provider": provider}
                )
        logger.info("Successfully seeded default AI providers and model catalog.")
