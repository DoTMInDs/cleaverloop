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
