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

class KlingProvider(BaseAIProvider):
    """
    Adapter for Kling AI API: Image-to-Video, Multi-shot, Character Consistency.
    """
    provider_slug = "kling"
    BASE_URL = "https://api.klingai.com/v1"

    def __init__(self):
        self.api_key = getattr(settings, 'KLING_API_KEY', '')

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(
            external_job_id="",
            status="failed",
            error_message="Kling provider specializes in video generation."
        )

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Kling AI API key is not configured.",
                retryable=False
            )
        try:
            # Kling standard task endpoint
            is_i2v = bool(request.reference_image_urls)
            endpoint = f"{self.BASE_URL}/videos/{'image2video' if is_i2v else 'text2video'}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {
                "model_name": model_id or "kling-v1-5",
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "duration": str(request.duration),
                "aspect_ratio": request.aspect_ratio,
            }
            if is_i2v:
                payload["image"] = request.reference_image_urls[0]

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    task_id = data.get("task_id", "")
                    return ProviderJobResult(
                        external_job_id=task_id,
                        status="queued",
                        raw_response=data
                    )
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"Kling API error ({resp.status_code}): {resp.text[:200]}"
                )
        except Exception as exc:
            logger.error(f"Kling video generation error: {exc}")
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if not self.api_key or not external_job_id:
            return ProviderJobResult(external_job_id=external_job_id, status="failed", error_message="Invalid request")
        try:
            url = f"{self.BASE_URL}/videos/tasks/{external_job_id}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    task_status = data.get("task_status", "").lower()
                    if task_status == "succeed":
                        video_url = data.get("task_result", {}).get("videos", [{}])[0].get("url")
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="completed",
                            output_media_url=video_url,
                            raw_response=data
                        )
                    elif task_status == "failed":
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="failed",
                            error_message=data.get("task_status_msg", "Kling task failed")
                        )
                    return ProviderJobResult(external_job_id=external_job_id, status="processing", raw_response=data)
        except Exception as exc:
            logger.error(f"Kling status check error: {exc}")
        return ProviderJobResult(external_job_id=external_job_id, status="processing")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        return CostEstimate(
            estimated_credits=80 + (request.duration * 60),
            estimated_duration_sec=request.duration,
            provider_cost_cents=float(request.duration * 25)
        )

    def health_check(self) -> bool:
        return bool(self.api_key)
