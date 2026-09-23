import uuid
from django.db import models
from django.conf import settings

def voice_sample_upload_path(instance, filename):
    ext = filename.split('.')[-1].lower() if '.' in filename else 'wav'
    unique_id = uuid.uuid4().hex[:12]
    return f"voices/samples/{instance.voice_profile.user_id}/{instance.voice_profile_id}/{unique_id}.{ext}"

class VoiceProfile(models.Model):
    """Personal neural voice profile cloned via ElevenLabs or custom audio models."""
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('neutral', 'Neutral / Ambiguous'),
        ('custom', 'Custom Character'),
    ]

    STATUS_CHOICES = [
        ('ready', 'Ready for Synthesis'),
        ('processing', 'Cloning Neural Weights'),
        ('failed', 'Cloning Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='voice_profiles'
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, help_text="Tone, cadence, and vocal persona description")
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, default='neutral')
    accent = models.CharField(max_length=60, blank=True, default='Neutral')
    language = models.CharField(max_length=40, default='en')

    provider = models.CharField(max_length=40, default='elevenlabs', help_text="Upstream engine (elevenlabs, fal, mock)")
    provider_voice_id = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text="Canonical remote voice ID (e.g. ElevenLabs voice_id)"
    )

    preview_audio = models.ForeignKey(
        'media.Media',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='preview_for_voice'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ready', db_index=True)
    error_message = models.TextField(blank=True)

    is_default = models.BooleanField(default=False)
    consent_confirmed = models.BooleanField(
        default=True,
        help_text="User affirmed legal consent and usage rights for this voice"
    )
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        unique_together = ('user', 'name')

    def __str__(self):
        return f"{self.name} ({self.get_gender_display()}) - {self.user.email}"

    @property
    def preview_url(self) -> str:
        """Accessible URL for the sample preview audio clip."""
        if self.preview_audio:
            return self.preview_audio.url
        first_sample = self.samples.first()
        if first_sample and first_sample.audio_file:
            return first_sample.audio_file.url
        return ""

    @property
    def sample_count(self) -> int:
        return self.samples.count()

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'provider_voice_id': self.provider_voice_id or str(self.id),
            'desc': self.description or f"{self.accent} {self.get_gender_display()} Voice",
            'gender': self.gender,
            'accent': self.accent,
            'badge': 'Cloned Voice',
            'is_cloned': True,
            'preview_url': self.preview_url,
            'status': self.status,
        }

class VoiceSample(models.Model):
    """
    Individual retained audio sample used to train and refine this voice clone.
    Permanently retained so users can inspect quality, re-train, or re-clone.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voice_profile = models.ForeignKey(
        VoiceProfile,
        on_delete=models.CASCADE,
        related_name='samples'
    )
    audio_file = models.FileField(upload_to=voice_sample_upload_path)
    duration_seconds = models.FloatField(default=0.0)
    file_size = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Sample ({self.duration_seconds:.1f}s) for {self.voice_profile.name}"

    @property
    def url(self) -> str:
        return self.audio_file.url if self.audio_file else ""
