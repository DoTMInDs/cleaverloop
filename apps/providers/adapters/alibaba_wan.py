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

class AlibabaWanProvider(BaseAIProvider):
    """
    Adapter for Alibaba Wan 2.1 open/efficient video generation model.
    Offers budget-friendly high-throughput video generation.
    """
    provider_slug = "wan"
    BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

    def __init__(self):
        self.api_key = getattr(settings, 'ALIBABA_API_KEY', '')

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(external_job_id="", status="failed", error_message="Wan model is for video.")

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Alibaba Wan API key is not configured.",
                retryable=False
            )
        try:
            endpoint = f"{self.BASE_URL}/services/aigc/video-generation/video-synthesis"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-DashScope-Async": "enable"
            }
            payload = {
                "model": model_id or "wan2.1-t2v-14b",
                "input": {"prompt": request.prompt},
                "parameters": {
                    "aspect_ratio": request.aspect_ratio,
                    "duration": request.duration
                }
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("output", {})
                    return ProviderJobResult(
                        external_job_id=data.get("task_id", ""),
                        status="queued",
                        raw_response=data
                    )
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"Alibaba Wan API error: {resp.text[:200]}"
                )
        except Exception as exc:
            logger.error(f"Alibaba Wan generation error: {exc}")
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if not self.api_key or not external_job_id:
            return ProviderJobResult(external_job_id=external_job_id, status="failed", error_message="Invalid request")
        try:
            url = f"{self.BASE_URL}/tasks/{external_job_id}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    output = resp.json().get("output", {})
                    task_status = output.get("task_status", "").upper()
                    if task_status == "SUCCEEDED":
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="completed",
                            output_media_url=output.get("video_url"),
                            raw_response=output
                        )
                    elif task_status == "FAILED":
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="failed",
                            error_message=output.get("message", "Wan generation failed")
                        )
                    return ProviderJobResult(external_job_id=external_job_id, status="processing", raw_response=output)
        except Exception as exc:
            logger.error(f"Wan status poll error: {exc}")
        return ProviderJobResult(external_job_id=external_job_id, status="processing")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        # Budget model pricing: 40 base + 30/sec
        return CostEstimate(
            estimated_credits=40 + (request.duration * 30),
            estimated_duration_sec=request.duration,
            provider_cost_cents=float(request.duration * 10)
        )

    def health_check(self) -> bool:
        return bool(self.api_key)
