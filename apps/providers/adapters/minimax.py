import logging
import httpx
from typing import Optional
from django.conf import settings
from apps.providers.base import (
    BaseAIProvider,
    GenerationRequest,
    ProviderJobResult,
    CostEstimate,
    load_image_as_data_uri
)

logger = logging.getLogger(__name__)

class MiniMaxProvider(BaseAIProvider):
    """
    Adapter for MiniMax / Hailuo AI Video Generation API (video-01).
    Supports text-to-video and image-to-video with cinematic physics and high motion fidelity.
    """
    provider_slug = "minimax"
    BASE_URL = "https://api.minimaxi.chat/v1"

    def __init__(self):
        self.api_key = getattr(settings, 'MINIMAX_API_KEY', '')

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        return ProviderJobResult(
            external_job_id="",
            status="failed",
            error_message="MiniMax adapter currently specializes in Hailuo video generation."
        )

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="MiniMax API key is not configured.",
                retryable=False
            )

        try:
            endpoint = f"{self.BASE_URL}/video_generation"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            model_name = "video-01"
            if model_id and "video" in model_id:
                model_name = "video-01"

            payload = {
                "model": model_name,
                "prompt": request.prompt,
                "prompt_optimizer": True
            }

            # If image-to-video reference provided, assign first_frame_image
            if request.reference_image_urls:
                ref_url = request.reference_image_urls[0]
                if ref_url.startswith(('http://', 'https://')):
                    payload["first_frame_image"] = ref_url
                else:
                    payload["first_frame_image"] = load_image_as_data_uri(ref_url) or ref_url

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    task_id = data.get("task_id", "")
                    base_resp = data.get("base_resp", {})
                    status_code = base_resp.get("status_code", 0)

                    if status_code != 0:
                        return ProviderJobResult(
                            external_job_id="",
                            status="failed",
                            error_message=f"MiniMax error: {base_resp.get('status_msg', 'Unknown error')}",
                            raw_response=data
                        )

                    return ProviderJobResult(
                        external_job_id=task_id,
                        status="queued",
                        raw_response=data
                    )

                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"MiniMax API HTTP {resp.status_code}: {resp.text[:200]}"
                )
        except Exception as exc:
            logger.error(f"MiniMax video generation error: {exc}", exc_info=True)
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if not self.api_key or not external_job_id:
            return ProviderJobResult(
                external_job_id=external_job_id,
                status="failed",
                error_message="Invalid request credentials or job ID"
            )

        try:
            url = f"{self.BASE_URL}/query/video_generation?task_id={external_job_id}"
            headers = {"Authorization": f"Bearer {self.api_key}"}

            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    task_status = data.get("status", "").strip().lower()

                    # MiniMax statuses: "Queueing", "Processing", "Success", "Fail"
                    if task_status == "success":
                        video_url = data.get("video_url") or data.get("file_url")
                        file_id = data.get("file_id")

                        # If direct URL isn't in task response, retrieve via file endpoint
                        if not video_url and file_id:
                            try:
                                retrieve_url = f"{self.BASE_URL}/files/retrieve?file_id={file_id}"
                                f_resp = client.get(retrieve_url, headers=headers)
                                if f_resp.status_code == 200:
                                    video_url = f_resp.json().get("file", {}).get("download_url")
                            except Exception as f_err:
                                logger.warning(f"Could not retrieve download_url for file {file_id}: {f_err}")

                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="completed",
                            output_media_url=video_url,
                            raw_response=data
                        )
                    elif task_status == "fail":
                        base_msg = data.get("base_resp", {}).get("status_msg", "MiniMax video generation failed")
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="failed",
                            error_message=base_msg,
                            raw_response=data
                        )
                    elif task_status in ["queueing", "queuing"]:
                        return ProviderJobResult(external_job_id=external_job_id, status="queued", raw_response=data)
                    else:
                        return ProviderJobResult(external_job_id=external_job_id, status="processing", raw_response=data)

        except Exception as exc:
            logger.error(f"MiniMax status polling error: {exc}")

        return ProviderJobResult(external_job_id=external_job_id, status="processing")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        duration = request.duration or 5
        return CostEstimate(
            estimated_credits=75 + (duration * 50),
            estimated_duration_sec=duration,
            provider_cost_cents=float(duration * 6.0)
        )

    def health_check(self) -> bool:
        return bool(self.api_key)
