import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify

class Character(models.Model):
    """Reusable AI character with visual and narrative consistency metadata."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='characters'
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, blank=True)
    description = models.TextField(blank=True, help_text="Short bio or background")
    appearance_description = models.TextField(
        help_text="Detailed visual traits: facial structure, hair color/style, eye color, age, build"
    )
    clothing_description = models.TextField(
        blank=True,
        help_text="Standard outfit or wardrobe style cues"
    )
    personality = models.TextField(blank=True, help_text="Behavioral and expression traits")
    voice_reference = models.ForeignKey(
        'media.Media',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='character_voice_for'
    )
    reference_images = models.ManyToManyField(
        'media.Media',
        blank=True,
        related_name='character_reference_for'
    )
    avatar = models.ImageField(upload_to='characters/avatars/', blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('owner', 'name')

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "char"
            self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.owner.email})"

    def build_prompt_cue(self) -> str:
        """Construct prompt modifier describing character traits."""
        cues = [f"Character: {self.name}"]
        if self.appearance_description:
            cues.append(self.appearance_description)
        if self.clothing_description:
            cues.append(f"Wearing: {self.clothing_description}")
        return ", ".join(cues)
