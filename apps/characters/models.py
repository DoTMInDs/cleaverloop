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
    parent_character = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='variants',
        help_text="Base character if this is an outfit, age, or universe variant"
    )
    variant_label = models.CharField(
        max_length=80,
        blank=True,
        help_text="e.g. Tactical Suit, Evening Gown, Older"
    )
    universe_style = models.CharField(
        max_length=64,
        blank=True,
        default='cinematic',
        help_text="Visual universe lock: cinematic, 3d_cgi, anime, claymation, vintage_cartoon, cyberpunk"
    )
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
            url = self.metadata['full_body_url']
            # Safeguard: Do not display stock showcase assets if character has a unique face anchor
            if any(k in url.lower() for k in ('marcus_vance', 'amina_diallo', 'amina_standing')):
                if self.face_anchor_url:
                    return self.face_anchor_url
                if self.avatar and not any(k in str(self.avatar).lower() for k in ('marcus_vance', 'amina_diallo')):
                    return self.avatar.url
            return url
        if self.face_anchor_url:
            return self.face_anchor_url
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

    def get_turnaround_angles(self) -> list:
        """Returns 4-angle orthographic turnaround sheet definitions for zero-drift 360° casting."""
        angles = (self.metadata or {}).get('turnaround_angles', [])
        if not angles:
            img = self.primary_image_url
            angles = [
                {
                    'id': 'front_ortho',
                    'label': 'Front Orthographic',
                    'icon': '🧍',
                    'image_url': img,
                    'prompt_cue': f'Front-facing orthographic full-body view of {self.name}, neutral studio lighting, symmetrical posture.'
                },
                {
                    'id': 'left_profile',
                    'label': 'Left 90° Profile',
                    'icon': '👈',
                    'image_url': img,
                    'prompt_cue': f'Strict 90-degree left side profile of {self.name}, consistent jawline and silhouette.'
                },
                {
                    'id': 'right_profile',
                    'label': 'Right 90° Profile',
                    'icon': '👉',
                    'image_url': img,
                    'prompt_cue': f'Strict 90-degree right side profile of {self.name}, matching wardrobe and hair geometry.'
                },
                {
                    'id': 'three_quarter_back',
                    'label': '3/4 Rear Silhouette',
                    'icon': '🔄',
                    'image_url': img,
                    'prompt_cue': f'Three-quarter over-the-shoulder rear view of {self.name}, showing back wardrobe details.'
                },
            ]
        return angles

    def get_expressions(self) -> list:
        """Returns facial expression matrix anchors for emotional performance control."""
        expressions = (self.metadata or {}).get('expressions', [])
        if not expressions:
            expressions = [
                {'id': 'neutral', 'label': 'Composed Neutral', 'icon': '😐', 'prompt_cue': 'calm, composed micro-expression with steady eye contact'},
                {'id': 'warm_smile', 'label': 'Warm Charismatic Smile', 'icon': '😊', 'prompt_cue': 'genuine warm smile with natural crinkles around the eyes'},
                {'id': 'intense_action', 'label': 'Intense Determination', 'icon': '😠', 'prompt_cue': 'fierce determined gaze, furrowed brow, high-stakes dramatic tension'},
                {'id': 'surprised_awe', 'label': 'Cinematic Awe / Shock', 'icon': '😮', 'prompt_cue': 'wide-eyed expression of sudden awe and emotional revelation'},
            ]
        return expressions

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
        if self.variant_label:
            cues.append(f"Variant: {self.variant_label}")
        if self.universe_style and self.universe_style != 'cinematic':
            cues.append(f"Style Universe: {self.universe_style.replace('_', ' ').title()}")
        if pose_cue:
            cues.append(f"Pose: {pose_cue}")
        return ", ".join(cues)


class SceneAsset(models.Model):
    """Reusable World-Building Asset: Locations (Environments) & Elements (Props/Vehicles/Artifacts)."""
    ASSET_TYPES = [
        ('location', 'Location / Environment'),
        ('element', 'Element / Prop / Vehicle'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scene_assets'
    )
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPES, default='location', db_index=True)
    name = models.CharField(max_length=120)
    category = models.CharField(
        max_length=80,
        blank=True,
        help_text="e.g. Interior, Exterior, Sci-Fi, Vehicle, Weapon, Artifact"
    )
    universe_style = models.CharField(max_length=64, blank=True, default='cinematic')
    time_of_day = models.CharField(max_length=40, blank=True, default='Golden Hour')
    weather = models.CharField(max_length=40, blank=True, default='Clear')
    description = models.TextField(blank=True)
    source_prompt = models.TextField(blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_asset_type_display()}] {self.name}"

    def build_prompt_cue(self) -> str:
        """Build a structured visual anchor prompt modifier for scenes using this Location or Element."""
        parts = [f"{self.get_asset_type_display()}: {self.name}"]
        if self.category:
            parts.append(f"Category: {self.category}")
        if self.asset_type == 'location':
            if self.time_of_day:
                parts.append(f"Time of Day: {self.time_of_day}")
            if self.weather:
                parts.append(f"Weather/Atmosphere: {self.weather}")
        if self.description:
            parts.append(self.description)
        if self.universe_style:
            parts.append(f"Visual Style: {self.universe_style.replace('_', ' ').title()}")
        return ", ".join(parts)

