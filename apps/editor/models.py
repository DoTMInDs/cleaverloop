import uuid
from django.db import models
from django.conf import settings

class AssemblyJob(models.Model):
    """Tracks asynchronous multi-scene video stitching and post-processing."""
    STATUS_CHOICES = [
        ('queued', 'Queued for Rendering'),
        ('rendering', 'Stitching Scenes with FFmpeg'),
        ('completed', 'Render Complete'),
        ('failed', 'Render Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='assembly_jobs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assembly_jobs'
    )
    target_aspect_ratio = models.CharField(max_length=10, default='16:9')
    background_music = models.ForeignKey(
        'media.Media',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='music_in_assembly'
    )
    output_video = models.ForeignKey(
        'media.Media',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assembly_output'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    render_log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Render Job {self.id} for {self.project.name} [{self.status}]"
