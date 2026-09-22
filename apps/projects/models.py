import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify

class Project(models.Model):
    """Creative project container organizing scenes, characters, and renders."""
    ASPECT_RATIOS = [
        ('16:9', 'Landscape (16:9)'),
        ('9:16', 'Portrait / Reel (9:16)'),
        ('1:1', 'Square (1:1)'),
        ('4:3', 'Classic (4:3)'),
        ('21:9', 'Cinematic Widescreen (21:9)'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active In-Progress'),
        ('rendering', 'Rendering Final Video'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='projects'
    )
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.ForeignKey(
        'media.Media',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='project_thumbnail_for'
    )
    aspect_ratio = models.CharField(max_length=10, choices=ASPECT_RATIOS, default='16:9')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    final_render = models.ForeignKey(
        'media.Media',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='final_render_project'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['owner', 'status', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "proj"
            self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.owner.email})"

    @property
    def total_duration(self) -> int:
        """Calculate total project duration from scenes."""
        return sum(s.duration for s in self.scenes.all())

class Scene(models.Model):
    """Individual storyboard scene in a project."""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='scenes'
    )
    order = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    prompt = models.TextField(help_text="Generative AI prompt for this scene")
    negative_prompt = models.TextField(blank=True)
    duration = models.PositiveIntegerField(default=5, help_text="Scene duration in seconds")
    camera_direction = models.CharField(
        max_length=120,
        blank=True,
        help_text="e.g. Pan left, Dolly zoom, Drone aerial shot, Close-up tracking"
    )
    visual_style = models.CharField(
        max_length=120,
        blank=True,
        help_text="e.g. Cinematic 35mm, Hyperrealistic, Moody neon lighting"
    )
    dialogue = models.TextField(blank=True)
    audio_direction = models.CharField(max_length=150, blank=True)
    characters = models.ManyToManyField(
        'characters.Character',
        blank=True,
        related_name='scenes'
    )
    character_references = models.ManyToManyField(
        'media.Media',
        blank=True,
        related_name='scenes_as_ref'
    )
    generated_media = models.ForeignKey(
        'media.Media',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='generated_scene'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        unique_together = ('project', 'order')

    def __str__(self):
        return f"Scene {self.order}: {self.title} ({self.project.name})"

    @property
    def latest_audio(self):
        """Fetch the most recent completed audio generation asset for this scene."""
        gen = self.generations.filter(generation_type='audio', status='completed').order_by('-created_at').first()
        return gen.output_media if gen else None

    @property
    def is_generating(self) -> bool:
        return self.status in ('queued', 'processing')

    @property
    def active_generation(self):
        return self.generations.filter(status__in=['queued', 'processing']).order_by('-created_at').first()

    @property
    def is_generating_audio(self) -> bool:
        active = self.active_generation
        return bool(active and active.generation_type == 'audio')

    @property
    def is_generating_video(self) -> bool:
        active = self.active_generation
        return bool(active and active.generation_type in ('video', 'image'))
