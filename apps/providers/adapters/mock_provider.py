import os
import uuid
import io
import time
from typing import Dict, Any
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageDraw, ImageFont

from apps.providers.base import (
    BaseAIProvider,
    GenerationRequest,
    ProviderJobResult,
    CostEstimate
)

# In-memory mock job state
_MOCK_JOBS: Dict[str, Dict[str, Any]] = {}

class MockAIProvider(BaseAIProvider):
    """
    High-fidelity deterministic mock provider for testing and development.
    Generates real media files (PNG/WebP) locally using Pillow without external API keys.
    """
    provider_slug = "mock"

    def _generate_synthetic_image(self, prompt: str, aspect_ratio: str, model_id: str) -> str:
        """Create a beautiful dark-mode synthetic image with metadata text."""
        # Calculate canvas dimensions based on aspect ratio
        dim_map = {
            '16:9': (1280, 720),
            '9:16': (720, 1280),
            '1:1': (1024, 1024),
            '4:3': (1024, 768),
            '21:9': (1400, 600),
        }
        width, height = dim_map.get(aspect_ratio, (1280, 720))

        # Create gradient obsidian canvas
        image = Image.new('RGB', (width, height), color=(10, 12, 18))
        draw = ImageDraw.Draw(image)

        # Draw sleek electric violet & cyan accents
        for i in range(12):
            draw.rectangle(
                [i, i, width - i - 1, height - i - 1],
                outline=(99 + i * 5, 102 + i * 2, 241 - i * 3)
            )

        # Draw decorative background grid
        for x in range(0, width, 80):
            draw.line([(x, 0), (x, height)], fill=(25, 30, 45), width=1)
        for y in range(0, height, 80):
            draw.line([(0, y), (width, y)], fill=(25, 30, 45), width=1)

        # Draw text overlays
        title = "CLEAVERLOOP AI - GENERATIVE STUDIO"
        model_info = f"Model: {model_id} | Aspect Ratio: {aspect_ratio} ({width}x{height})"
        prompt_preview = f"Prompt: {prompt[:80]}..." if len(prompt) > 80 else f"Prompt: {prompt}"

        # Draw simple text boxes
        draw.text((60, 60), title, fill=(255, 255, 255))
        draw.text((60, 100), model_info, fill=(160, 175, 210))
        draw.text((60, 140), prompt_preview, fill=(129, 140, 248))
        draw.text((60, height - 80), "STATUS: RENDER COMPLETE (SYNTHETIC FIXTURE)", fill=(52, 211, 153))

        # Save to memory
        buf = io.BytesIO()
        image.save(buf, format='PNG', optimize=True)
        buf.seek(0)

        # Save to default storage
        filename = f"mock_outputs/{uuid.uuid4().hex[:12]}.png"
        saved_path = default_storage.save(filename, ContentFile(buf.getvalue()))
        return default_storage.url(saved_path)

    def _generate_synthetic_video(self, prompt: str, aspect_ratio: str, duration: int, model_id: str) -> str:
        """Create an animated multi-frame WebP video-like asset using Pillow."""
        dim_map = {
            '16:9': (854, 480),
            '9:16': (480, 854),
            '1:1': (640, 640),
        }
        width, height = dim_map.get(aspect_ratio, (854, 480))
        frames = []
        num_frames = min(duration * 2, 12)  # 2 frames per second for mock

        for f in range(num_frames):
            frame = Image.new('RGB', (width, height), color=(8, 10, 16))
            draw = ImageDraw.Draw(frame)

            # Pulsing color animation
            pulse_color = (
                int(80 + (f / num_frames) * 120),
                int(70 + (f / num_frames) * 80),
                int(220 - (f / num_frames) * 60)
            )
            draw.rectangle([10, 10, width - 11, height - 11], outline=pulse_color, width=4)

            # Draw moving indicator
            circle_x = int(100 + (f / num_frames) * (width - 200))
            draw.ellipse([circle_x - 30, height // 2 - 30, circle_x + 30, height // 2 + 30], fill=pulse_color)

            draw.text((40, 40), f"CLEAVERLOOP AI VIDEO RENDER [{model_id}]", fill=(255, 255, 255))
            draw.text((40, 70), f"Frame {f+1}/{num_frames} | Duration: {duration}s | {aspect_ratio}", fill=(180, 190, 220))
            draw.text((40, height - 60), f"Prompt: {prompt[:60]}", fill=(130, 150, 250))

            frames.append(frame)

        buf = io.BytesIO()
        frames[0].save(
            buf,
            format='WEBP',
            save_all=True,
            append_images=frames[1:],
            duration=500,
            loop=0
        )
        buf.seek(0)

        filename = f"mock_outputs/{uuid.uuid4().hex[:12]}.webp"
        saved_path = default_storage.save(filename, ContentFile(buf.getvalue()))
        return default_storage.url(saved_path)

    def generate_image(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        job_id = f"mock-img-{uuid.uuid4().hex[:10]}"
        
        # Test failure trigger for verifying refund pipeline
        if "fail" in request.prompt.lower() or "error" in request.prompt.lower():
            result = ProviderJobResult(
                external_job_id=job_id,
                status="failed",
                error_message="Mock provider simulated an upstream generation failure for testing.",
                retryable=False
            )
            _MOCK_JOBS[job_id] = result
            return result

        output_url = self._generate_synthetic_image(request.prompt, request.aspect_ratio, model_id)
        result = ProviderJobResult(
            external_job_id=job_id,
            status="completed",
            output_media_url=output_url,
            thumbnail_url=output_url,
            raw_response={"mock": True, "model": model_id, "prompt": request.prompt}
        )
        _MOCK_JOBS[job_id] = result
        return result

    def generate_video(self, model_id: str, request: GenerationRequest) -> ProviderJobResult:
        job_id = f"mock-vid-{uuid.uuid4().hex[:10]}"

        # Test failure trigger for verifying refund pipeline
        if "fail" in request.prompt.lower() or "error" in request.prompt.lower():
            result = ProviderJobResult(
                external_job_id=job_id,
                status="failed",
                error_message="Mock provider simulated video render failure.",
                retryable=False
            )
            _MOCK_JOBS[job_id] = result
            return result

        output_url = self._generate_synthetic_video(request.prompt, request.aspect_ratio, request.duration, model_id)
        result = ProviderJobResult(
            external_job_id=job_id,
            status="completed",
            output_media_url=output_url,
            thumbnail_url=output_url,
            raw_response={"mock": True, "model": model_id, "duration": request.duration}
        )
        _MOCK_JOBS[job_id] = result
        return result

    def get_status(self, external_job_id: str) -> ProviderJobResult:
        if external_job_id in _MOCK_JOBS:
            return _MOCK_JOBS[external_job_id]
        return ProviderJobResult(
            external_job_id=external_job_id,
            status="completed",
            raw_response={"mock": True}
        )

    def cancel(self, external_job_id: str) -> bool:
        if external_job_id in _MOCK_JOBS:
            _MOCK_JOBS[external_job_id].status = "cancelled"
            return True
        return False

    def estimate_cost(self, model_id: str, request: GenerationRequest) -> CostEstimate:
        credits = 50 if "img" in model_id or "image" in model_id else (50 + request.duration * 50)
        return CostEstimate(
            estimated_credits=credits,
            estimated_duration_sec=request.duration,
            provider_cost_cents=0.0
        )

    def health_check(self) -> bool:
        return True
