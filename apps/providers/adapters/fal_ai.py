import logging
import httpx
from typing import Optional, Dict, Any
from django.conf import settings
from apps.providers.base import (
    BaseAIProvider,
    GenerationRequest,
    ProviderJobResult,
    CostEstimate,
    load_image_as_data_uri
)

logger = logging.getLogger(__name__)

class FalAIProvider(BaseAIProvider):
    """
    Universal Multi-Model Adapter for Fal.ai API.
    Hosts Wan 2.1, Luma Dream Machine, CogVideoX-5B, and Flux Pro with unified billing.
    """
    provider_slug = "fal"
    BASE_QUEUE_URL = "https://queue.fal.run"

    # Map internal model IDs to Fal.ai model endpoints
    MODEL_MAP = {
        "fal-wan-2.1": "fal-ai/wan-t2v",
        "fal-wan-2.1-i2v": "fal-ai/wan-i2v",
        "fal-luma-dream-machine": "fal-ai/luma-dream-machine/ray-2/image-to-video",
        "fal-cogvideox-5b": "fal-ai/cogvideox-5b",
        "fal-flux-pro": "fal-ai/flux-pro/v1.1",
        "fal-flux-schnell": "fal-ai/flux/schnell",
    }

    def __init__(self):
        self.api_key = getattr(settings, 'FAL_KEY', '')

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json"
        }

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Fal.ai API key (FAL_KEY) is not configured.",
                retryable=False
            )

        target_model = self.MODEL_MAP.get(model_id, "fal-ai/flux/schnell")
        endpoint = f"{self.BASE_QUEUE_URL}/{target_model}"

        # Map aspect ratio
        size_map = {
            "16:9": "landscape_16_9",
            "9:16": "portrait_16_9",
            "1:1": "square_hd",
            "4:3": "landscape_4_3"
        }
        payload = {
            "prompt": request.prompt,
            "image_size": size_map.get(request.aspect_ratio, "landscape_16_9"),
            "num_images": 1
        }
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

        return self._submit_queue_job(endpoint, target_model, payload)

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Fal.ai API key (FAL_KEY) is not configured.",
                retryable=False
            )

        # If reference image is present and model is Wan, use i2v endpoint
        is_i2v = bool(request.reference_image_urls)
        if "wan" in model_id and is_i2v:
            target_model = self.MODEL_MAP.get("fal-wan-2.1-i2v", "fal-ai/wan-i2v")
        else:
            target_model = self.MODEL_MAP.get(model_id, "fal-ai/wan-t2v")

        endpoint = f"{self.BASE_QUEUE_URL}/{target_model}"

        aspect_map = {
            "16:9": "16:9",
            "9:16": "9:16",
            "1:1": "1:1"
        }
        payload: Dict[str, Any] = {
            "prompt": request.prompt,
            "aspect_ratio": aspect_map.get(request.aspect_ratio, "16:9")
        }

        if is_i2v:
            ref_url = request.reference_image_urls[0]
            if ref_url.startswith(('http://', 'https://')):
                payload["image_url"] = ref_url
            else:
                payload["image_url"] = load_image_as_data_uri(ref_url) or ref_url

        return self._submit_queue_job(endpoint, target_model, payload)

    def _submit_queue_job(self, endpoint: str, target_model: str, payload: Dict[str, Any]) -> ProviderJobResult:
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload, headers=self._get_headers())
                if resp.status_code in (200, 201, 202):
                    data = resp.json()
                    request_id = data.get("request_id", "")
                    # Encode model into external_job_id so polling knows which endpoint to query
                    compound_id = f"{target_model}::{request_id}"
                    return ProviderJobResult(
                        external_job_id=compound_id,
                        status="queued",
                        raw_response=data
                    )
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"Fal.ai API error ({resp.status_code}): {resp.text[:300]}"
                )
        except Exception as exc:
            logger.error(f"Fal.ai submission error: {exc}", exc_info=True)
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if not self.api_key or not external_job_id:
            return ProviderJobResult(external_job_id=external_job_id, status="failed", error_message="Invalid request")

        try:
            if "::" in external_job_id:
                target_model, request_id = external_job_id.split("::", 1)
            else:
                target_model = "fal-ai/wan-t2v"
                request_id = external_job_id

            status_url = f"{self.BASE_QUEUE_URL}/{target_model}/requests/{request_id}/status"
            result_url = f"{self.BASE_QUEUE_URL}/{target_model}/requests/{request_id}"

            with httpx.Client(timeout=15.0) as client:
                resp = client.get(status_url, headers=self._get_headers())
                if resp.status_code == 200:
                    status_data = resp.json()
                    status_str = status_data.get("status", "").upper()

                    if status_str == "COMPLETED":
                        # Fetch the final output payload
                        res_resp = client.get(result_url, headers=self._get_headers())
                        if res_resp.status_code == 200:
                            result_data = res_resp.json()
                            media_url = None
                            if "video" in result_data and isinstance(result_data["video"], dict):
                                media_url = result_data["video"].get("url")
                            elif "images" in result_data and isinstance(result_data["images"], list) and result_data["images"]:
                                media_url = result_data["images"][0].get("url")

                            return ProviderJobResult(
                                external_job_id=external_job_id,
                                status="completed",
                                output_media_url=media_url,
                                raw_response=result_data
                            )
                    elif status_str in ("FAILED", "ERROR"):
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="failed",
                            error_message=status_data.get("error", "Fal.ai task processing failed"),
                            raw_response=status_data
                        )
                    elif status_str == "IN_QUEUE":
                        return ProviderJobResult(external_job_id=external_job_id, status="queued", raw_response=status_data)
                    else:
                        return ProviderJobResult(external_job_id=external_job_id, status="processing", raw_response=status_data)

        except Exception as exc:
            logger.error(f"Fal.ai status polling error: {exc}")

        return ProviderJobResult(external_job_id=external_job_id, status="processing")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        duration = request.duration or 5
        return CostEstimate(
            estimated_credits=70 + (duration * 40),
            estimated_duration_sec=duration,
            provider_cost_cents=float(duration * 4.0)
        )

    def health_check(self) -> bool:
        return bool(self.api_key)
