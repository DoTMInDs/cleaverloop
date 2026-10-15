import logging
import httpx
from django.conf import settings
from apps.providers.base import (
    BaseAIProvider,
    GenerationRequest,
    ProviderJobResult,
    CostEstimate
)
from apps.providers.diagnostics import _resolve_api_key

logger = logging.getLogger(__name__)

class SeedanceProvider(BaseAIProvider):
    """
    Adapter for ByteDance / BytePlus ModelArk Seedance 2.5 and Seedance 2.0 video generation.
    Connects to BytePlus ModelArk (ap-southeast) and supports text-to-video, image-to-video,
    and synchronized audio.
    """
    provider_slug = "seedance"
    BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"
    DEFAULT_MODEL = "dreamina-seedance-2-5-260628"

    def __init__(self):
        self.api_key = _resolve_api_key('SEEDANCE_API_KEY')
        self.custom_model = _resolve_api_key('SEEDANCE_MODEL_ID') or _resolve_api_key('SEEDANCE_ENDPOINT_ID')

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(external_job_id="", status="failed", error_message="Seedance focuses on video.")

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            self.api_key = _resolve_api_key('SEEDANCE_API_KEY')

        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Seedance / BytePlus API key is not configured.",
                retryable=False
            )
        try:
            target_model = self.custom_model or model_id or self.DEFAULT_MODEL
            if target_model in ("seedance", "seedance-2.5", "seedance-2"):
                target_model = self.custom_model or self.DEFAULT_MODEL

            endpoint = f"{self.BASE_URL}/contents/generations/tasks"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            content = [
                {
                    "type": "text",
                    "text": request.prompt
                }
            ]
            if request.reference_image_urls:
                for img_url in request.reference_image_urls:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": img_url}
                    })

            payload = {
                "model": target_model,
                "content": content
            }

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code in (200, 201, 202):
                    data = resp.json()
                    task_id = data.get("id") or data.get("task_id", "")
                    return ProviderJobResult(
                        external_job_id=task_id,
                        status="queued",
                        raw_response=data
                    )
                err_text = resp.text[:400]
                if "ModelNotOpen" in err_text:
                    err_msg = (
                        f"Seedance model '{target_model}' has not been activated in your BytePlus Ark Console. "
                        "Please go to BytePlus Console -> ModelArk -> Foundation Models, click 'Activate' on Seedance 2.5 "
                        "(or create an Endpoint in Ark and set SEEDANCE_MODEL_ID in .env)."
                    )
                else:
                    err_msg = f"BytePlus ModelArk API error ({resp.status_code}): {err_text}"
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=err_msg
                )
        except Exception as exc:
            logger.error(f"Seedance generation error: {exc}")
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if not self.api_key or not external_job_id:
            return ProviderJobResult(external_job_id=external_job_id, status="failed", error_message="Invalid request")
        try:
            url = f"{self.BASE_URL}/contents/generations/tasks/{external_job_id}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    status_raw = str(data.get("status", "")).lower()
                    if status_raw in ("succeeded", "completed", "success"):
                        content = data.get("content") or {}
                        video_url = ""
                        if isinstance(content, dict):
                            video_url = content.get("video_url") or content.get("url") or ""
                        elif isinstance(content, list) and content:
                            video_url = content[0].get("video_url") or content[0].get("url") or ""
                        elif isinstance(data.get("result"), dict):
                            video_url = data["result"].get("video_url") or ""

                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="completed",
                            output_media_url=video_url,
                            raw_response=data
                        )
                    elif status_raw in ("failed", "error", "expired"):
                        err = data.get("error") or {}
                        err_msg = err.get("message") if isinstance(err, dict) else str(err)
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="failed",
                            error_message=err_msg or "Seedance render error",
                            raw_response=data
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

