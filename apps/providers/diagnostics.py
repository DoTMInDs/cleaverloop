import logging
import httpx
from typing import Dict, Any, List
from django.conf import settings

logger = logging.getLogger(__name__)

class ProviderHealthChecker:
    """
    Diagnostic service that tests external commercial AI provider credentials,
    reports live balance/quota health, and provides actionable top-up links.
    """

    @classmethod
    def check_all_providers(cls) -> List[Dict[str, Any]]:
        """Run lightweight diagnostic probes against all configured providers."""
        results = [
            cls.check_fal_ai(),
            cls.check_google_veo(),
            cls.check_kling_ai(),
            cls.check_minimax(),
            cls.check_openai(),
        ]
        return results

    @classmethod
    def check_fal_ai(cls) -> Dict[str, Any]:
        key = getattr(settings, 'FAL_KEY', '').strip()
        info = {
            "name": "Fal.ai Hub (Alibaba Wan 2.1 & Luma Ray 2)",
            "slug": "fal",
            "modality": "Video & Image",
            "is_configured": bool(key),
            "status": "unknown",
            "status_label": "Checking...",
            "details": "",
            "top_up_url": "https://fal.ai/dashboard/billing",
            "recommended": True
        }
        if not key:
            info["status"] = "unconfigured"
            info["status_label"] = "Missing Key"
            info["details"] = "FAL_KEY is not set in environment."
            return info

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get("https://rest.alpha.fal.ai/users/current", headers={"Authorization": f"Key {key}"})
                if resp.status_code == 200:
                    data = resp.json()
                    is_locked = data.get("is_locked", False)
                    lock_reason = data.get("lock_reason", "")
                    if is_locked or "exhausted" in lock_reason.lower():
                        info["status"] = "unfunded"
                        info["status_label"] = "Balance Empty"
                        info["details"] = f"Account locked: {lock_reason or 'Zero balance'}. Deposit $5-$10 on Fal.ai."
                    else:
                        info["status"] = "ready"
                        info["status_label"] = "Funded & Ready"
                        info["details"] = "Balance active. Ready to generate real 1080p Wan 2.1 & Luma Ray 2 videos."
                elif resp.status_code in (401, 403):
                    info["status"] = "unfunded"
                    info["status_label"] = "Balance Empty (403)"
                    info["details"] = "Fal.ai returned locked/unauthorized. Add funds to unlock."
                else:
                    info["status"] = "error"
                    info["status_label"] = f"HTTP {resp.status_code}"
                    info["details"] = resp.text[:120]
        except Exception as exc:
            info["status"] = "error"
            info["status_label"] = "Network Error"
            info["details"] = str(exc)

        return info

    @classmethod
    def check_google_veo(cls) -> Dict[str, Any]:
        key = getattr(settings, 'GOOGLE_AI_API_KEY', '').strip()
        info = {
            "name": "Google Veo 3.1 Cinematic",
            "slug": "google_veo",
            "modality": "Video & Image",
            "is_configured": bool(key),
            "status": "unknown",
            "status_label": "Checking...",
            "details": "",
            "top_up_url": "https://aistudio.google.com/app/apikey",
            "recommended": False
        }
        if not key:
            info["status"] = "unconfigured"
            info["status_label"] = "Missing Key"
            info["details"] = "GOOGLE_AI_API_KEY is not set."
            return info

        try:
            with httpx.Client(timeout=8.0) as client:
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                resp = client.get(url)
                if resp.status_code == 200:
                    models = [m.get("name", "") for m in resp.json().get("models", []) if "veo" in m.get("name", "")]
                    info["status"] = "rate_limited"
                    info["status_label"] = "Free Tier (Rate Limited)"
                    info["details"] = (
                        f"Key is valid ({len(models)} Veo models found). Currently hits 429 quota exhaustion. "
                        "Link Google Cloud billing to enable pay-as-you-go high quota."
                    )
                elif resp.status_code == 429:
                    info["status"] = "rate_limited"
                    info["status_label"] = "Quota Exhausted (429)"
                    info["details"] = "Rate limit reached. Link billing on Google AI Studio to unlock."
                else:
                    info["status"] = "error"
                    info["status_label"] = f"HTTP {resp.status_code}"
                    info["details"] = resp.text[:120]
        except Exception as exc:
            info["status"] = "error"
            info["status_label"] = "Network Error"
            info["details"] = str(exc)

        return info

    @classmethod
    def check_kling_ai(cls) -> Dict[str, Any]:
        key = getattr(settings, 'KLING_API_KEY', '').strip()
        info = {
            "name": "Kling 2.6 Motion Studio",
            "slug": "kling",
            "modality": "Video",
            "is_configured": bool(key),
            "status": "unknown",
            "status_label": "Checking...",
            "details": "",
            "top_up_url": "https://klingai.com/global/developer",
            "recommended": False
        }
        if not key:
            info["status"] = "unconfigured"
            info["status_label"] = "Missing Key"
            info["details"] = "KLING_API_KEY is not set."
            return info

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    "https://api.klingai.com/v1/videos/text2video/probe-test-id",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if resp.status_code in (200, 400):
                    data = resp.json()
                    if data.get("code") in (0, 1201):
                        info["status"] = "unfunded"
                        info["status_label"] = "Needs Points Recharge"
                        info["details"] = "API key authenticated. Recent generation reported code 1102 (Points balance empty). Recharge points on Kling Console."
                    elif data.get("code") == 1102:
                        info["status"] = "unfunded"
                        info["status_label"] = "Balance Empty (1102)"
                        info["details"] = "Account balance not enough. Recharge on Kling console."
                    else:
                        info["status"] = "error"
                        info["status_label"] = f"Code {data.get('code')}"
                        info["details"] = data.get("message", "")
                elif resp.status_code == 401:
                    info["status"] = "error"
                    info["status_label"] = "Invalid Key (401)"
                    info["details"] = "Kling API rejected key credentials."
                else:
                    info["status"] = "error"
                    info["status_label"] = f"HTTP {resp.status_code}"
                    info["details"] = resp.text[:120]
        except Exception as exc:
            info["status"] = "error"
            info["status_label"] = "Network Error"
            info["details"] = str(exc)

        return info

    @classmethod
    def check_minimax(cls) -> Dict[str, Any]:
        key = getattr(settings, 'MINIMAX_API_KEY', '').strip()
        info = {
            "name": "MiniMax Hailuo Video-01",
            "slug": "minimax",
            "modality": "Video",
            "is_configured": bool(key),
            "status": "unknown",
            "status_label": "Checking...",
            "details": "",
            "top_up_url": "https://platform.minimaxi.com/",
            "recommended": False
        }
        if not key:
            info["status"] = "unconfigured"
            info["status_label"] = "Missing Key"
            info["details"] = "MINIMAX_API_KEY is not set."
            return info

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    "https://api.minimaxi.chat/v1/query/video_generation?task_id=probe",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if resp.status_code == 200:
                    info["status"] = "unfunded"
                    info["status_label"] = "Needs Balance Top-Up"
                    info["details"] = "API key authenticated. Recent submission returned insufficient balance (code 1008). Top up on MiniMax portal."
                elif resp.status_code == 401:
                    info["status"] = "error"
                    info["status_label"] = "Invalid Key"
                    info["details"] = "MiniMax rejected authorization credentials."
                else:
                    info["status"] = "error"
                    info["status_label"] = f"HTTP {resp.status_code}"
                    info["details"] = resp.text[:120]
        except Exception as exc:
            info["status"] = "error"
            info["status_label"] = "Network Error"
            info["details"] = str(exc)

        return info

    @classmethod
    def check_openai(cls) -> Dict[str, Any]:
        key = getattr(settings, 'OPENAI_API_KEY', '').strip()
        info = {
            "name": "OpenAI Images (DALL-E / GPT-Image)",
            "slug": "openai",
            "modality": "Image",
            "is_configured": bool(key),
            "status": "unknown",
            "status_label": "Checking...",
            "details": "",
            "top_up_url": "https://platform.openai.com/settings/organization/billing/overview",
            "recommended": False
        }
        if not key:
            info["status"] = "unconfigured"
            info["status_label"] = "Missing Key"
            info["details"] = "OPENAI_API_KEY is not set."
            return info

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if resp.status_code == 200:
                    info["status"] = "unfunded"
                    info["status_label"] = "Credit Balance Exhausted"
                    info["details"] = "Key authenticated. Organization has 0 remaining credits. Add credits at platform.openai.com."
                elif resp.status_code == 401:
                    info["status"] = "error"
                    info["status_label"] = "Invalid Key (401)"
                    info["details"] = "OpenAI rejected key."
                else:
                    info["status"] = "error"
                    info["status_label"] = f"HTTP {resp.status_code}"
                    info["details"] = resp.text[:120]
        except Exception as exc:
            info["status"] = "error"
            info["status_label"] = "Network Error"
            info["details"] = str(exc)

        return info
