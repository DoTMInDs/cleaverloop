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

class OpenAIProvider(BaseAIProvider):
    """
    Adapter for OpenAI Image Generation (DALL-E 3 / GPT Image).
    """
    provider_slug = "openai"
    BASE_URL = "https://api.openai.com/v1"

    def __init__(self):
        self.api_key = getattr(settings, 'OPENAI_API_KEY', '')

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="OpenAI API key is not configured.",
                retryable=False
            )
        try:
            endpoint = f"{self.BASE_URL}/images/generations"
            headers = {"Authorization": f"Bearer {self.api_key}"}

            # Map aspect ratio to DALL-E 3 sizes
            size_map = {
                '1:1': "1024x1024",
                '16:9': "1792x1024",
                '9:16': "1024x1792",
            }
            size = size_map.get(request.aspect_ratio, "1024x1024")

            payload = {
                "model": model_id or "dall-e-3",
                "prompt": request.prompt,
                "n": 1,
                "size": size,
                "quality": "standard" if request.quality != "hd" else "hd"
            }
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    img_data = data.get("data", [{}])[0]
                    img_url = img_data.get("url")
                    return ProviderJobResult(
                        external_job_id=f"openai-img-{request.correlation_id[:8]}",
                        status="completed",
                        output_media_url=img_url,
                        thumbnail_url=img_url,
                        raw_response=data
                    )
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"OpenAI error: {resp.text[:200]}"
                )
        except Exception as exc:
            logger.error(f"OpenAI image generation error: {exc}")
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(external_job_id="", status="failed", error_message="Video not supported on this adapter.")

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        return ProviderJobResult(external_job_id=external_job_id, status="completed")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        return CostEstimate(
            estimated_credits=50,
            estimated_duration_sec=0,
            provider_cost_cents=4.0
        )

    def health_check(self) -> bool:
        return bool(self.api_key)
