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

class FluxProvider(BaseAIProvider):
    """
    Adapter for Black Forest Labs Flux 1.1 Pro / Flux Schnell image models.
    """
    provider_slug = "flux"
    BASE_URL = "https://api.bfl.ml/v1"

    def __init__(self):
        self.api_key = getattr(settings, 'FLUX_API_KEY', '')

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Flux API key is not configured.",
                retryable=False
            )
        try:
            endpoint = f"{self.BASE_URL}/{model_id or 'flux-pro-1.1'}"
            headers = {"x-key": self.api_key}
            payload = {
                "prompt": request.prompt,
                "aspect_ratio": request.aspect_ratio,
                "output_format": "jpeg",
            }
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
                    error_message=f"Flux API error: {resp.text[:200]}"
                )
        except Exception as exc:
            logger.error(f"Flux submission error: {exc}")
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(external_job_id="", status="failed", error_message="Flux generates images.")

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if not self.api_key or not external_job_id:
            return ProviderJobResult(external_job_id=external_job_id, status="failed", error_message="Invalid request")
        try:
            url = f"{self.BASE_URL}/get_result?id={external_job_id}"
            headers = {"x-key": self.api_key}
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status", "").lower()
                    if status == "ready":
                        result_url = data.get("result", {}).get("sample")
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="completed",
                            output_media_url=result_url,
                            thumbnail_url=result_url,
                            raw_response=data
                        )
                    elif status in ("failed", "error"):
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="failed",
                            error_message="Flux image generation failed."
                        )
                    return ProviderJobResult(external_job_id=external_job_id, status="processing", raw_response=data)
        except Exception as exc:
            logger.error(f"Flux polling error: {exc}")
        return ProviderJobResult(external_job_id=external_job_id, status="processing")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        return CostEstimate(
            estimated_credits=45,
            estimated_duration_sec=0,
            provider_cost_cents=3.0
        )

    def health_check(self) -> bool:
        return bool(self.api_key)
