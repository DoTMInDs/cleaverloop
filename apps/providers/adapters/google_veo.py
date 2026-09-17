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

class GoogleVeoProvider(BaseAIProvider):
    """
    Adapter for Google Gemini API Veo video models (Veo 3.1 Standard, Fast, Lite)
    and Google Imagen/Nano Banana image models.
    """
    provider_slug = "google"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self):
        self.api_key = getattr(settings, 'GOOGLE_AI_API_KEY', '')

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        """Submit Imagen 3 or Nano Banana generation."""
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Google AI API key is not configured.",
                retryable=False
            )
        try:
            # Google Gemini Imagen endpoint
            endpoint = f"{self.BASE_URL}/models/{model_id}:predict?key={self.api_key}"
            payload = {
                "instances": [{"prompt": request.prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": request.aspect_ratio,
                    "outputMimeType": "image/jpeg"
                }
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    # Google returns base64 predictions
                    predictions = data.get("predictions", [])
                    if predictions and "bytesBase64Encoded" in predictions[0]:
                        b64_data = predictions[0]["bytesBase64Encoded"]
                        return ProviderJobResult(
                            external_job_id=f"veo-img-{request.correlation_id[:8]}",
                            status="completed",
                            raw_response={"data_base64_length": len(b64_data)}
                        )
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"Google API error: {resp.status_code} - {resp.text[:200]}"
                )
        except Exception as exc:
            logger.error(f"Google Imagen generation failed: {exc}")
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        """Submit Google Veo 3.1 cinematic video generation."""
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Google AI API key is not configured.",
                retryable=False
            )
        try:
            endpoint = f"{self.BASE_URL}/models/{model_id}:predictLongRunning?key={self.api_key}"
            payload = {
                "prompt": request.prompt,
                "negativePrompt": request.negative_prompt,
                "aspectRatio": request.aspect_ratio,
                "durationSeconds": request.duration,
            }
            if request.reference_image_urls:
                payload["imageInput"] = {"uri": request.reference_image_urls[0]}

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload)
                if resp.status_code in (200, 202):
                    data = resp.json()
                    operation_name = data.get("name", "")
                    return ProviderJobResult(
                        external_job_id=operation_name or f"veo-op-{request.correlation_id[:8]}",
                        status="queued",
                        raw_response=data
                    )
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"Google Veo API error ({resp.status_code}): {resp.text[:200]}"
                )
        except Exception as exc:
            logger.error(f"Google Veo submission failed: {exc}")
            return ProviderJobResult(external_job_id="", status="failed", error_message=str(exc))

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        """Poll Google long-running operation."""
        if not self.api_key or not external_job_id:
            return ProviderJobResult(external_job_id=external_job_id, status="failed", error_message="Invalid request")
        try:
            url = f"{self.BASE_URL}/{external_job_id}?key={self.api_key}"
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("done"):
                        if "error" in data:
                            return ProviderJobResult(
                                external_job_id=external_job_id,
                                status="failed",
                                error_message=data["error"].get("message", "Veo generation error")
                            )
                        # Extract video output uri
                        res = data.get("response", {})
                        video_uri = res.get("videoUri") or res.get("outputUri")
                        return ProviderJobResult(
                            external_job_id=external_job_id,
                            status="completed",
                            output_media_url=video_uri,
                            raw_response=data
                        )
                    return ProviderJobResult(external_job_id=external_job_id, status="processing", raw_response=data)
        except Exception as exc:
            logger.error(f"Google Veo status polling error: {exc}")
        return ProviderJobResult(external_job_id=external_job_id, status="processing")

    def cancel(self, external_job_id: str) -> bool:
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        # Veo standard: 100 base + 75/sec
        return CostEstimate(
            estimated_credits=100 + (request.duration * 75),
            estimated_duration_sec=request.duration,
            provider_cost_cents=float(request.duration * 30)
        )

    def health_check(self) -> bool:
        return bool(self.api_key)
