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
    voice_profile = models.ForeignKey(
        'voices.VoiceProfile',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='characters'
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

    @property
    def primary_image_url(self) -> str:
        """Returns the full-length standing character figure URL or avatar URL."""
        if self.metadata and self.metadata.get('full_body_url'):
            return self.metadata['full_body_url']
        if self.avatar:
            return self.avatar.url
        return ""

    @property
    def face_anchor_url(self) -> str:
        """Returns the 100% likeness isolated face anchor URL if available."""
        if self.metadata:
            return self.metadata.get('original_face_url') or self.metadata.get('face_anchor_url') or ""
        return ""

    def get_poses(self) -> list:
        """Returns list of pose dictionary objects configured for this character."""
        poses = self.metadata.get('poses', [])
        if not poses and self.avatar:
            poses = [{
                'id': 'default_pose',
                'label': 'Standing Figure',
                'icon': '🧍',
                'image_url': self.avatar.url,
                'prompt_cue': 'In standard full-body standing posture.'
            }]
        return poses

    def build_prompt_cue(self, pose_cue: str = "") -> str:
        """Construct prompt modifier describing character traits, gender, body shape, and optional pose."""
        gender = (self.metadata.get('gender') or '').lower()
        if gender == 'female':
            gender_cue = f"Female character ({self.name}, woman in an authentic realistic feminine pose with natural weight shift and graceful feminine silhouette)"
        elif gender == 'male':
            gender_cue = f"Male character ({self.name}, man with masculine physique)"
        else:
            gender_cue = f"Character: {self.name}"

        cues = [gender_cue]

        body_type = self.metadata.get('body_type')
        if body_type:
            cues.append(f"Physique: {body_type}")

        if self.appearance_description:
            cues.append(self.appearance_description)
        if self.clothing_description:
            cues.append(f"Wearing: {self.clothing_description}")
        if pose_cue:
            cues.append(f"Pose: {pose_cue}")
        return ", ".join(cues)
