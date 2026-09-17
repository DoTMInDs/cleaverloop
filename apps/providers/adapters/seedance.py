import logging
import httpx
from django.conf import settings
from apps.providers.base import (
    BaseAIProvider,
    GenerationRequest,
    ProviderJobResult,
    CostEstimate
)

logger = logging.getLogger(__name__)

class SeedanceProvider(BaseAIProvider):
    """
    Adapter for ByteDance Seedance 2.0 and Seedance 2.5 video generation.
    Supports multimodal references, longer duration, and synchronized audio.
    """
    provider_slug = "seedance"
    BASE_URL = "https://api.seedance.ai/v1"

    def __init__(self):
        self.api_key = getattr(settings, 'SEEDANCE_API_KEY', '')

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(external_job_id="", status="failed", error_message="Seedance focuses on video.")

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Seedance API key is not configured.",
                retryable=False
            )
        try:
            endpoint = f"{self.BASE_URL}/videos/generations"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {
                "model": model_id or "seedance-2.5",
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "duration": request.duration,
                "aspect_ratio": request.aspect_ratio,
                "audio_enabled": True,
            }
            if request.reference_image_urls:
                payload["image_references"] = request.reference_image_urls

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code in (200, 201, 202):
                    data = resp.json()
                    return ProviderJobResult(
                        external_job_id=data.get("id", ""),
                        status="queued",
                        raw_response=data
                    )
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"Seedance API error: {resp.text[:200]}"
                )
        except Exception as exc:
            logger.error(f"Seedance generation error: {exc}")
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if not self.api_key or not external_job_id:
            return ProviderJobResult(external_job_id=external_job_id, status="failed", error_message="Invalid request")
        try:
            url = f"{self.BASE_URL}/videos/generations/{external_job_id}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    state = data.get("status", "").lower()
                    if state == "completed":
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="completed",
                            output_media_url=data.get("video_url"),
                            raw_response=data
                        )
                    elif state == "failed":
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="failed",
                            error_message=data.get("error", "Seedance render error")
                        )
                    return ProviderJobResult(external_job_id=external_job_id, status="processing", raw_response=data)
        except Exception as exc:
            logger.error(f"Seedance status error: {exc}")
        return ProviderJobResult(external_job_id=external_job_id, status="processing")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        return CostEstimate(
            estimated_credits=75 + (request.duration * 50),
            estimated_duration_sec=request.duration,
            provider_cost_cents=float(request.duration * 20)
        )

    def health_check(self) -> bool:
        return bool(self.api_key)
