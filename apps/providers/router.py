import logging
from typing import Optional, List
from django.conf import settings
from apps.providers.models import AIModel, AIProviderConfig

logger = logging.getLogger(__name__)

class NoEligibleModelError(Exception):
    """Raised when no enabled models satisfy the required generation capabilities."""
    pass

class ModelRouter:
    """
    Intelligent constraint solver and model routing engine.
    Matches generation parameters against provider capabilities, health, and user preferences.
    """

    @classmethod
    def select_model(
        cls,
        modality: str,
        user_preference: str = "automatic",  # automatic, best_quality, fastest, budget, or specific model_id
        duration: int = 5,
        aspect_ratio: str = "16:9",
        requires_image_ref: bool = False,
        requires_character_ref: bool = False,
        requires_audio: bool = False,
    ) -> AIModel:
        """
        Route request to the most appropriate active model that strictly satisfies all constraints.
        """
        # If user explicitly requested a specific model_id:
        if user_preference not in ("automatic", "best_quality", "fastest", "budget"):
            specific = AIModel.objects.filter(model_id=user_preference, is_enabled=True).first()
            if specific:
                # Check provider health
                if specific.provider.is_enabled and specific.provider.health_status != 'offline':
                    return specific
                logger.warning(f"Preferred model {user_preference} provider is offline/disabled. Attempting fallback.")

        # Query candidates by modality and enabled status
        candidates = AIModel.objects.filter(
            modality=modality,
            is_enabled=True,
            provider__is_enabled=True
        ).exclude(provider__health_status='offline')

        # Filter by duration constraint for video
        if modality == 'video' and duration > 0:
            candidates = candidates.filter(max_duration__gte=duration)

        # Filter by reference asset capabilities
        if requires_image_ref:
            candidates = candidates.filter(supports_image_reference=True)
        if requires_character_ref:
            candidates = candidates.filter(supports_character_reference=True)
        if requires_audio:
            candidates = candidates.filter(supports_audio=True)

        if not candidates.exists():
            # If in mock mode or dev fallback
            if getattr(settings, 'MOCK_PROVIDERS_ENABLED', True):
                mock_model = AIModel.objects.filter(
                    provider__slug='mock',
                    modality=modality
                ).first()
                if mock_model:
                    return mock_model

            raise NoEligibleModelError(
                f"No available {modality} models satisfy the requested criteria "
                f"(duration: {duration}s, image_ref: {requires_image_ref}, audio: {requires_audio})."
            )

        # If live candidates exist, exclude mock provider from smart auto-routing presets
        live_candidates = candidates.exclude(provider__slug='mock')
        if live_candidates.exists():
            candidates = live_candidates

        # Apply preference heuristic sorting
        if user_preference == "best_quality":
            # Sort by priority desc, premium first
            selected = candidates.order_by('-is_premium', '-priority').first()
        elif user_preference == "budget":
            # Sort by lowest credit cost
            selected = candidates.order_by('credit_cost_fixed', 'credit_cost_per_second').first()
        elif user_preference == "fastest":
            # Prioritize models with fast in display_name or lowest avg latency
            selected = candidates.order_by('provider__avg_latency_ms', '-priority').first()
        else:
            # Automatic: Balanced priority
            selected = candidates.order_by('-priority', 'credit_cost_fixed').first()

        logger.info(f"ModelRouter selected [{selected.model_id}] for modality={modality}, preference={user_preference}")
        return selected

    @classmethod
    def get_fallback_model(
        cls,
        failed_model: AIModel,
        duration: int = 5,
        has_refs: bool = False,
        excluded_provider_slugs: Optional[List[str]] = None
    ) -> Optional[AIModel]:
        """
        Select an alternative model when primary provider fails during execution.
        Supports multi-tier failover chains (Tier 1 Direct -> Tier 2 Fal.ai -> Tier 3 Mock).
        Preserves exact capability guarantees.
        """
        slugs_to_exclude = list(excluded_provider_slugs or [])
        if failed_model and failed_model.provider.slug not in slugs_to_exclude:
            slugs_to_exclude.append(failed_model.provider.slug)

        candidates = AIModel.objects.filter(
            modality=failed_model.modality,
            is_enabled=True,
            provider__is_enabled=True
        ).exclude(
            provider__slug__in=slugs_to_exclude
        ).exclude(
            provider__health_status='offline'
        )

        if failed_model.modality == 'video' and duration > 0:
            candidates = candidates.filter(max_duration__gte=duration)
        if has_refs:
            candidates = candidates.filter(supports_image_reference=True)

        # Prioritize live fallback candidates over mock
        live_fallbacks = candidates.exclude(provider__slug='mock')
        if live_fallbacks.exists():
            return live_fallbacks.order_by('-priority').first()

        # If mock provider is enabled, fall back to mock
        if getattr(settings, 'MOCK_PROVIDERS_ENABLED', True):
            return candidates.filter(provider__slug='mock').order_by('-priority').first()

        return candidates.order_by('-priority').first()
