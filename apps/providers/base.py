from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class GenerationRequest:
    prompt: str
    negative_prompt: str = ""
    aspect_ratio: str = "16:9"
    duration: int = 5
    quality: str = "standard"
    seed: Optional[int] = None
    reference_image_urls: List[str] = field(default_factory=list)
    character_prompt_enhancement: str = ""
    extra_params: Dict[str, Any] = field(default_factory=dict)
    webhook_url: Optional[str] = None
    correlation_id: str = ""

@dataclass
class ProviderJobResult:
    external_job_id: str
    status: str  # "queued", "processing", "completed", "failed"
    output_media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    retryable: bool = False

@dataclass
class CostEstimate:
    estimated_credits: int
    estimated_duration_sec: int
    provider_cost_cents: float = 0.0

class BaseAIProvider(ABC):
    """Abstract Base Class for all AI model provider adapters."""
    provider_slug: str

    @abstractmethod
    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        """Submit text-to-image or image-to-image request."""
        pass

    @abstractmethod
    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        """Submit text-to-video or image-to-video request."""
        pass

    @abstractmethod
    def get_status(self, external_job_id: str) -> ProviderJobResult:
        """Poll the current status of an in-flight job."""
        pass

    @abstractmethod
    def cancel(self, external_job_id: str) -> bool:
        """Cancel an in-flight job if supported."""
        pass

    @abstractmethod
    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        """Calculate estimated credits and provider costs."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check availability and connectivity of provider endpoint."""
        pass

def load_image_as_base64(image_path_or_url: str) -> Optional[str]:
    """
    Read an image from local media storage or path and return raw base64 string.
    Works for relative media paths (/media/...), filenames, or file system paths.
    """
    if not image_path_or_url:
        return None

    # If already a data URI or raw base64
    if image_path_or_url.startswith('data:') and ';base64,' in image_path_or_url:
        return image_path_or_url.split(';base64,', 1)[1]

    # Clean local media prefix
    clean_path = image_path_or_url
    if clean_path.startswith('/media/'):
        clean_path = clean_path[len('/media/'):]
    elif clean_path.startswith('media/'):
        clean_path = clean_path[len('media/'):]

    # 1. Try Django default_storage
    try:
        from django.core.files.storage import default_storage
        if default_storage.exists(clean_path):
            with default_storage.open(clean_path, 'rb') as f:
                import base64
                return base64.b64encode(f.read()).decode('utf-8')
    except Exception:
        pass

    # 2. Try filesystem MEDIA_ROOT
    try:
        import os
        from django.conf import settings
        media_root = getattr(settings, 'MEDIA_ROOT', '')
        full_path = os.path.join(str(media_root), clean_path)
        if os.path.exists(full_path):
            with open(full_path, 'rb') as f:
                import base64
                return base64.b64encode(f.read()).decode('utf-8')
    except Exception:
        pass

    # 3. If external HTTP/HTTPS URL, download and encode
    if image_path_or_url.startswith(('http://', 'https://')):
        try:
            import httpx
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(image_path_or_url)
                if resp.status_code == 200:
                    import base64
                    return base64.b64encode(resp.content).decode('utf-8')
        except Exception:
            pass

    return None

def load_image_as_data_uri(image_path_or_url: str, default_mime: str = "image/png") -> Optional[str]:
    """Convert an image path or URL into a data:image/...;base64,... URI."""
    if not image_path_or_url:
        return None
    if image_path_or_url.startswith('data:'):
        return image_path_or_url

    b64 = load_image_as_base64(image_path_or_url)
    if b64:
        ext = image_path_or_url.lower()
        if ext.endswith(('.jpg', '.jpeg')):
            mime = "image/jpeg"
        elif ext.endswith('.webp'):
            mime = "image/webp"
        else:
            mime = default_mime
        return f"data:{mime};base64,{b64}"

    return image_path_or_url if image_path_or_url.startswith(('http://', 'https://')) else None
