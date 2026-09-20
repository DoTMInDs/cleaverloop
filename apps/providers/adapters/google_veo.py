import logging
import httpx
from django.conf import settings
from apps.providers.base import (
    BaseAIProvider,
    GenerationRequest,
    ProviderJobResult,
    CostEstimate,
    load_image_as_base64
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
        """Submit Imagen 3 or Gemini image generation."""
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Google AI API key is not configured.",
                retryable=False
            )
        try:
            target_model = model_id
            if target_model in ["imagen-3.0-generate-002", "imagen-3.0", "google-imagen"]:
                target_model = "gemini-2.5-flash-image"

            with httpx.Client(timeout=30.0) as client:
                # 1. Try Gemini AI Studio generateContent endpoint
                endpoint = f"{self.BASE_URL}/models/{target_model}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": request.prompt}
                            ]
                        }
                    ]
                }
                resp = client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            inline_data = part.get("inlineData", {})
                            b64_data = inline_data.get("data")
                            if b64_data:
                                import base64
                                from django.core.files.base import ContentFile
                                from django.core.files.storage import default_storage
                                img_bytes = base64.b64decode(b64_data)
                                mime = inline_data.get("mimeType", "image/jpeg")
                                ext = "png" if "png" in mime else "jpg"
                                filename = f"google_outputs/{request.correlation_id[:12]}.{ext}"
                                saved_path = default_storage.save(filename, ContentFile(img_bytes))
                                output_url = default_storage.url(saved_path)

                                return ProviderJobResult(
                                    external_job_id=f"gemini-img-{request.correlation_id[:8]}",
                                    status="completed",
                                    output_media_url=output_url,
                                    thumbnail_url=output_url,
                                    raw_response={"data_base64_length": len(b64_data), "saved_path": saved_path}
                                )

                # 2. Try legacy Imagen predict endpoint
                predict_endpoint = f"{self.BASE_URL}/models/{model_id}:predict?key={self.api_key}"
                predict_payload = {
                    "instances": [{"prompt": request.prompt}],
                    "parameters": {
                        "sampleCount": 1,
                        "aspectRatio": request.aspect_ratio,
                        "outputMimeType": "image/jpeg"
                    }
                }
                resp_predict = client.post(predict_endpoint, json=predict_payload)
                if resp_predict.status_code == 200:
                    data = resp_predict.json()
                    predictions = data.get("predictions", [])
                    if predictions and "bytesBase64Encoded" in predictions[0]:
                        import base64
                        from django.core.files.base import ContentFile
                        from django.core.files.storage import default_storage
                        b64_data = predictions[0]["bytesBase64Encoded"]
                        img_bytes = base64.b64decode(b64_data)
                        filename = f"google_outputs/{request.correlation_id[:12]}.jpg"
                        saved_path = default_storage.save(filename, ContentFile(img_bytes))
                        output_url = default_storage.url(saved_path)

                        return ProviderJobResult(
                            external_job_id=f"veo-img-{request.correlation_id[:8]}",
                            status="completed",
                            output_media_url=output_url,
                            thumbnail_url=output_url,
                            raw_response={"data_base64_length": len(b64_data), "saved_path": saved_path}
                        )

                err_msg = resp.text[:200] if resp.status_code != 200 else resp_predict.text[:200]
                return ProviderJobResult(
                    external_job_id="",
                    status="failed",
                    error_message=f"Google API error: {resp.status_code} - {err_msg}"
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
            # Map model aliases to Google AI Studio model IDs
            target_model = model_id
            if target_model in ["veo-3.1-standard", "veo-3.1"]:
                target_model = "veo-3.1-generate-preview"
            elif target_model in ["veo-3.1-fast"]:
                target_model = "veo-3.1-fast-generate-preview"

            endpoint = f"{self.BASE_URL}/models/{target_model}:predictLongRunning?key={self.api_key}"

            # Google Veo duration must be 4 or 8 seconds
            duration_sec = 4 if (request.duration or 5) <= 5 else 8

            instance_data = {"prompt": request.prompt}
            if request.reference_image_urls:
                ref_path = request.reference_image_urls[0]
                b64_str = load_image_as_base64(ref_path)
                if b64_str:
                    mime = "image/jpeg"
                    if ref_path.lower().endswith(".png"):
                        mime = "image/png"
                    elif ref_path.lower().endswith(".webp"):
                        mime = "image/webp"
                    instance_data["image"] = {
                        "bytesBase64Encoded": b64_str,
                        "mimeType": mime
                    }


            parameters = {
                "aspectRatio": request.aspect_ratio or "16:9",
                "durationSeconds": duration_sec,
                "sampleCount": 1
            }
            if request.negative_prompt:
                parameters["negativePrompt"] = request.negative_prompt

            payload = {
                "instances": [instance_data],
                "parameters": parameters
            }

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
                    error_message=f"Google Veo API error ({resp.status_code}): {resp.text[:400]}"
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
