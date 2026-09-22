import logging
import httpx
from typing import Optional, Dict, Any
from django.conf import settings
from apps.providers.base import (
    BaseAIProvider,
    GenerationRequest,
    ProviderJobResult,
    CostEstimate,
    load_image_as_data_uri,
    load_media_as_data_uri
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
        "fal-mmaudio-v2": "fal-ai/mmaudio-v2",
        "fal-kokoro": "fal-ai/kokoro",
        "fal-stable-audio": "fal-ai/stable-audio",
        "fal-sync-lipsync": "fal-ai/sync-lipsync",
        "fal-latentsync": "fal-ai/latentsync",
        "fal-live-portrait": "fal-ai/live-portrait",
    }

    def __init__(self):
        self.api_key = getattr(settings, 'FAL_KEY', '')

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json"
        }

    def generate_audio(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Fal.ai API key (FAL_KEY) is not configured.",
                retryable=False
            )

        if "mmaudio" in model_id:
            video_url = None
            if request.reference_image_urls:
                v = request.reference_image_urls[0]
                if v.startswith(('http://', 'https://')) and not ('127.0.0.1' in v or 'localhost' in v):
                    video_url = v

            payload: Dict[str, Any] = {
                "prompt": request.prompt or "cinematic atmospheric foley and sound effects",
                "duration": float(request.duration or 5.0)
            }
            if video_url:
                payload["video_url"] = video_url
                submit_endpoint = f"{self.BASE_QUEUE_URL}/fal-ai/mmaudio-v2"
            else:
                submit_endpoint = f"{self.BASE_QUEUE_URL}/fal-ai/mmaudio-v2/text-to-audio"
                
            return self._submit_queue_job(submit_endpoint, "fal-ai/mmaudio-v2", payload)

        elif "kokoro" in model_id or "tts" in model_id:
            target_model = self.MODEL_MAP.get("fal-kokoro", "fal-ai/kokoro/american-english")
            endpoint = f"{self.BASE_QUEUE_URL}/{target_model}"
            payload = {
                "prompt": request.prompt,
                "voice": "af_heart"
            }
            return self._submit_queue_job(endpoint, target_model, payload)

        else:
            target_model = self.MODEL_MAP.get("fal-stable-audio", "fal-ai/stable-audio")
            endpoint = f"{self.BASE_QUEUE_URL}/{target_model}"
            payload = {
                "prompt": request.prompt,
                "seconds_total": int(request.duration or 10)
            }
            return self._submit_queue_job(endpoint, target_model, payload)

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

    def _upload_local_media_to_fal(self, media_path_or_url: str) -> str:
        """
        Upload local media file to Fal.ai CDN via fal_client to prevent request payload size errors.
        Falls back to data URI if upload is not possible.
        """
        if not media_path_or_url:
            return ""

        # If already a remote public HTTP/HTTPS URL, pass as is
        if media_path_or_url.startswith(('http://', 'https://')) and not ('127.0.0.1' in media_path_or_url or 'localhost' in media_path_or_url):
            return media_path_or_url

        # Check local filesystem
        import os
        from django.conf import settings

        local_path = None
        clean_path = media_path_or_url.replace('\\', '/')
        if clean_path.startswith('/media/'):
            clean_path = clean_path[len('/media/'):]
        elif clean_path.startswith('media/'):
            clean_path = clean_path[len('media/'):]
        clean_path = clean_path.lstrip('/')

        media_root = os.path.abspath(str(getattr(settings, 'MEDIA_ROOT', '')))
        candidate_path = os.path.abspath(os.path.join(media_root, clean_path))
        if os.path.exists(candidate_path):
            local_path = candidate_path
        elif os.path.exists(media_path_or_url):
            local_path = os.path.abspath(media_path_or_url)

        if local_path and os.path.exists(local_path):
            try:
                import fal_client
                if self.api_key:
                    os.environ['FAL_KEY'] = self.api_key
                uploaded_url = fal_client.upload_file(local_path)
                if uploaded_url and uploaded_url.startswith(('http://', 'https://')):
                    logger.info(f"Uploaded local file {local_path} to Fal CDN: {uploaded_url}")
                    return uploaded_url
            except Exception as exc:
                logger.warning(f"Could not upload {local_path} to Fal CDN via fal_client: {exc}")

        # Fallback to data URI if upload was unavailable
        return load_media_as_data_uri(media_path_or_url) or media_path_or_url

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        if not self.api_key:
            return ProviderJobResult(
                external_job_id="",
                status="failed",
                error_message="Fal.ai API key (FAL_KEY) is not configured.",
                retryable=False
            )

        # 1. Neural Lip-Sync & Video Dubbing
        if "lipsync" in model_id.lower() or "latentsync" in model_id.lower():
            target_model = self.MODEL_MAP.get(model_id, "fal-ai/sync-lipsync")
            endpoint = f"{self.BASE_QUEUE_URL}/{target_model}"
            video_url = request.extra_params.get("video_url") or ""
            audio_url = request.extra_params.get("audio_url") or ""

            # Disambiguate video and audio from reference_image_urls if not explicitly passed
            if not video_url or not audio_url:
                for ref in (request.reference_image_urls or []):
                    ref_lower = ref.lower()
                    is_audio = any(ref_lower.endswith(ext) or f"audio/{ext}" in ref_lower for ext in ('.mp3', '.wav', '.ogg', '.m4a', '.aac', 'mp3', 'wav', 'ogg'))
                    is_video = any(ref_lower.endswith(ext) or f"video/{ext}" in ref_lower for ext in ('.mp4', '.mov', '.avi', '.webm', 'mp4', 'mov', 'avi'))
                    if is_audio and not audio_url:
                        audio_url = ref
                    elif is_video and not video_url:
                        video_url = ref
                    elif not video_url:
                        video_url = ref
                    elif not audio_url:
                        audio_url = ref

            # Upload local files to Fal CDN so request payload doesn't exceed size limits
            video_url = self._upload_local_media_to_fal(video_url)
            audio_url = self._upload_local_media_to_fal(audio_url)

            payload: Dict[str, Any] = {
                "video_url": video_url,
                "audio_url": audio_url,
                "sync_mode": request.extra_params.get("sync_mode", "cut_off"),
            }
            return self._submit_queue_job(endpoint, target_model, payload)

        # 2. Standard Text-to-Video & Image-to-Video
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
        payload = {
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

            # Normalize target_model in case sub-paths were passed
            if target_model.startswith("fal-ai/mmaudio-v2"):
                target_model = "fal-ai/mmaudio-v2"

            status_url = f"{self.BASE_QUEUE_URL}/{target_model}/requests/{request_id}/status"
            result_url = f"{self.BASE_QUEUE_URL}/{target_model}/requests/{request_id}"

            timeout_cfg = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=30.0)
            with httpx.Client(timeout=timeout_cfg) as client:
                resp = client.get(status_url, headers=self._get_headers(), params={"logs": False})
                if resp.status_code in (200, 202):
                    status_data = resp.json()
                    status_str = status_data.get("status", "").upper()

                    if status_str == "COMPLETED":
                        # Fetch the final output payload
                        res_resp = client.get(result_url, headers=self._get_headers())
                        if res_resp.status_code == 200:
                            result_data = res_resp.json()
                            media_url = None
                            if "video" in result_data and isinstance(result_data["video"], dict):
                                media_url = result_data["video"].get("url") or result_data["video"].get("file_url")
                            elif "video" in result_data and isinstance(result_data["video"], str):
                                media_url = result_data["video"]
                            elif "images" in result_data and isinstance(result_data["images"], list) and result_data["images"]:
                                first_img = result_data["images"][0]
                                media_url = first_img.get("url") if isinstance(first_img, dict) else str(first_img)
                            elif "audio" in result_data and isinstance(result_data["audio"], dict):
                                media_url = result_data["audio"].get("url")
                            elif "audio_file" in result_data and isinstance(result_data["audio_file"], dict):
                                media_url = result_data["audio_file"].get("url")
                            elif "audio" in result_data and isinstance(result_data["audio"], str):
                                media_url = result_data["audio"]
                            elif "audio_file" in result_data and isinstance(result_data["audio_file"], str):
                                media_url = result_data["audio_file"]
                            elif "audio_url" in result_data:
                                media_url = result_data.get("audio_url")
                            elif "url" in result_data and isinstance(result_data["url"], str):
                                media_url = result_data["url"]
                            elif "file_url" in result_data and isinstance(result_data["file_url"], str):
                                media_url = result_data["file_url"]

                            return ProviderJobResult(
                                external_job_id=external_job_id,
                                status="completed",
                                output_media_url=media_url,
                                raw_response=result_data
                            )
                        else:
                            # Handle result errors (e.g. 422 Unprocessable Entity, 400, 500)
                            try:
                                err_data = res_resp.json()
                                if "detail" in err_data:
                                    if isinstance(err_data["detail"], list):
                                        err_msg = "; ".join([d.get("msg", str(d)) for d in err_data["detail"] if isinstance(d, dict)])
                                    else:
                                        err_msg = str(err_data["detail"])
                                elif "error" in err_data:
                                    err_msg = str(err_data["error"])
                                else:
                                    err_msg = res_resp.text[:300]
                            except Exception:
                                err_msg = res_resp.text[:300]
                            return ProviderJobResult(
                                external_job_id=external_job_id,
                                status="failed",
                                error_message=f"Fal.ai job failed ({res_resp.status_code}): {err_msg}",
                                raw_response={"status_code": res_resp.status_code, "text": res_resp.text[:500]}
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
                elif resp.status_code in (400, 401, 402, 403, 404, 422):
                    try:
                        err_msg = resp.json().get("detail", resp.text[:200])
                    except Exception:
                        err_msg = resp.text[:200]
                    return ProviderJobResult(
                        external_job_id=external_job_id,
                        status="failed",
                        error_message=f"Fal.ai error ({resp.status_code}): {err_msg}",
                        raw_response={"status_code": resp.status_code}
                    )

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
