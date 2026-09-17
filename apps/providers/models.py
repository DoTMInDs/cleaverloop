import uuid
from django.db import models

class AIProviderConfig(models.Model):
    """Configuration and health tracking for an integrated AI provider."""
    HEALTH_STATUSES = [
        ('healthy', 'Healthy (Operational)'),
        ('degraded', 'Degraded (High Latency/Timeouts)'),
        ('offline', 'Offline (Unavailable)'),
    ]

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    is_enabled = models.BooleanField(default=True)
    health_status = models.CharField(max_length=20, choices=HEALTH_STATUSES, default='healthy')
    consecutive_failures = models.PositiveIntegerField(default=0)
    avg_latency_ms = models.PositiveIntegerField(default=1200)
    last_health_check = models.DateTimeField(null=True, blank=True)
    api_key_env_var = models.CharField(max_length=100, blank=True, help_text="Name of environment variable storing secret key")
    webhook_secret_env_var = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'AI Provider Config'
        verbose_name_plural = 'AI Provider Configs'
        ordering = ['name']

    def __str__(self):
        status_icon = "🟢" if self.health_status == 'healthy' else ("🟡" if self.health_status == 'degraded' else "🔴")
        return f"{status_icon} {self.name} ({self.slug})"

class AIModel(models.Model):
    """Dynamic model catalog entry configured via admin without redeployments."""
    MODALITIES = [
        ('video', 'Video Generation'),
        ('image', 'Image Generation'),
        ('audio', 'Audio / Voice'),
        ('multimodal', 'Multimodal'),
    ]

    provider = models.ForeignKey(
        AIProviderConfig,
        on_delete=models.CASCADE,
        related_name='models'
    )
    model_id = models.CharField(max_length=120, unique=True, help_text="Canonical model identifier sent to adapter")
    display_name = models.CharField(max_length=150)
    modality = models.CharField(max_length=20, choices=MODALITIES, default='video')
    
    # Capabilities matrix
    capabilities = models.JSONField(
        default=list,
        blank=True,
        help_text="List of capability flags: ['t2v', 'i2v', 'audio', 'character_ref', 'multishot', 'upscale']"
    )
    max_duration = models.PositiveIntegerField(default=10, help_text="Max video duration in seconds (0 for images)")
    supported_resolutions = models.JSONField(default=list, blank=True, help_text="e.g. ['720p', '1080p', '4k']")
    supported_aspect_ratios = models.JSONField(default=list, blank=True, help_text="e.g. ['16:9', '9:16', '1:1']")
    
    supports_audio = models.BooleanField(default=False)
    supports_image_reference = models.BooleanField(default=False)
    supports_video_reference = models.BooleanField(default=False)
    supports_character_reference = models.BooleanField(default=False)

    # Internal credit pricing configuration
    credit_cost_fixed = models.PositiveIntegerField(default=50, help_text="Fixed base credit cost per generation")
    credit_cost_per_second = models.PositiveIntegerField(default=50, help_text="Additional credit cost per video second")
    
    # Routing heuristics
    is_enabled = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=10, help_text="Higher value = prioritized by model router")
    is_premium = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'AI Model'
        verbose_name_plural = 'AI Models'
        ordering = ['-priority', 'display_name']

    def __str__(self):
        return f"{self.display_name} [{self.model_id}] ({self.provider.name})"

    def calculate_credit_cost(self, duration: int = 5) -> int:
        """Calculate total required credits based on modality and duration."""
        if self.modality == 'image':
            return self.credit_cost_fixed
        return self.credit_cost_fixed + (self.credit_cost_per_second * duration)
