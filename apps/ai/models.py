import uuid
from django.db import models
from django.conf import settings


DEFAULT_AGENT_SKILLS = [
    {
        'slug': 'general',
        'name': 'Autonomous Cinema Director',
        'icon': '🎬',
        'category': 'Cinema',
        'description': 'Balanced multi-scene director for narrative films, trailers, and storytelling.',
        'system_directive': 'Direct with theatrical pacing, purposeful camera movement, and strong visual continuity.',
        'default_aspect_ratio': '16:9',
    },
    {
        'slug': 'viral_reel',
        'name': 'Viral Hook & Reel Architect',
        'icon': '🔥',
        'category': 'Social',
        'description': 'High-retention 9:16 vertical storytelling with a 2-second visual hook and fast kinetic cuts.',
        'system_directive': 'Open with an immediate scroll-stopping visual hook in Scene 1, high-contrast lighting, and vertical 9:16 framing.',
        'default_aspect_ratio': '9:16',
    },
    {
        'slug': 'commercial_ad',
        'name': 'Brand & Product Commercial Director',
        'icon': '💎',
        'category': 'Commercial',
        'description': 'Luxury macro product cinematography, hero lighting, and persuasive brand storytelling.',
        'system_directive': 'Emphasize tactile surface textures, studio rim lighting, clean hero product framing, and aspirational brand finish.',
        'default_aspect_ratio': '16:9',
    },
    {
        'slug': 'anime_showrunner',
        'name': 'Anime & Stylized Action Showrunner',
        'icon': '⚡',
        'category': 'Animation',
        'description': 'Sakuga keyframe motion, dramatic speed lines, anamorphic lens flares, and expressive framing.',
        'system_directive': 'Use expressive anime sakuga cinematography, dramatic low-angle foreshortening, and vibrant cel-shaded lighting.',
        'default_aspect_ratio': '16:9',
    },
    {
        'slug': 'documentary_essay',
        'name': 'Visual Documentary Essayist',
        'icon': '🌍',
        'category': 'Documentary',
        'description': 'Atmospheric B-roll, observational camera work, and thoughtful narrative voiceover cues.',
        'system_directive': 'Combine intimate observational close-ups with sweeping environmental establishing shots and articulate narration.',
        'default_aspect_ratio': '16:9',
    },
]


DEFAULT_VIRAL_EFFECTS = [
    {
        'slug': 'liquid-gold-metamorphosis',
        'name': 'Liquid Gold Metamorphosis',
        'category': 'Transformation',
        'icon': '✨',
        'description': 'Subject smoothly transforms into molten 24k reflective gold with volumetric studio sparks.',
        'prompt_template': 'Cinematic macro transformation: {subject} smoothly morphing into molten 24k liquid gold, specular metallic reflections, slow-motion golden droplets and volumetric studio rim lighting, photorealistic 8k VFX.',
        'aspect_ratio': '9:16',
        'duration': 5,
    },
    {
        'slug': 'cyber-hologram-materialize',
        'name': 'Cyber Hologram Materialize',
        'category': 'Sci-Fi VFX',
        'icon': '💠',
        'description': 'Neon cyan and orange volumetric laser grid scans and materializes the subject in mid-air.',
        'prompt_template': 'High-tech volumetric laser scan: {subject} materializing out of glowing cyan and electric orange holographic voxel particles in a dark futuristic chamber, anamorphic lens flare, crisp 60fps VFX.',
        'aspect_ratio': '9:16',
        'duration': 5,
    },
    {
        'slug': 'miniature-tilt-shift-world',
        'name': 'Miniature Tilt-Shift Toy World',
        'category': 'Stylized',
        'icon': '🧸',
        'description': 'Turns any scene or character into a handcrafted stop-motion miniature diorama with macro depth of field.',
        'prompt_template': 'Macro tilt-shift stop-motion diorama of {subject}, handcrafted miniature textures, shallow f/1.4 macro depth of field, warm tabletop studio lighting, playful kinetic motion.',
        'aspect_ratio': '16:9',
        'duration': 5,
    },
    {
        'slug': 'orbital-bullet-time-freeze',
        'name': '360° Orbital Bullet-Time',
        'category': 'Camera Rig',
        'icon': '🌀',
        'description': 'Time freezes in mid-air while a high-speed camera orbits 360 degrees around the hero subject.',
        'prompt_template': 'Matrix-style 360-degree orbital bullet-time camera rig spinning rapidly around {subject} frozen in mid-air amidst suspended rain droplets and floating debris, dramatic rim lighting.',
        'aspect_ratio': '16:9',
        'duration': 5,
    },
    {
        'slug': 'velvet-cloud-inflation',
        'name': 'Surreal Velvet Balloon Inflation',
        'category': 'Viral Surreal',
        'icon': '🎈',
        'description': 'Subject inflates into a glossy, weightless couture balloon floating gently above the street.',
        'prompt_template': 'Surreal viral VFX shot: {subject} inflating into a buoyant, glossy velvet-textured balloon and floating weightlessly upward under golden hour sunlight, ultra-realistic cloth physics.',
        'aspect_ratio': '9:16',
        'duration': 5,
    },
    {
        'slug': 'thunder-god-awakening',
        'name': 'Storm & Lightning Awakening',
        'category': 'Action VFX',
        'icon': '⚡',
        'description': 'Crackling plasma arcs erupt around the subject’s eyes and hands as the camera pushes in.',
        'prompt_template': 'Epic cinematic power awakening: {subject} surrounded by crackling electric blue and amber plasma lightning arcs, wind sweeping through the frame, dramatic slow push-in camera movement.',
        'aspect_ratio': '9:16',
        'duration': 5,
    },
]


class AgentConversation(models.Model):
    """Persistent multi-turn Super Agent session with clarifying Q&A and linked storyboard project."""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('clarifying', 'Awaiting Clarification'),
        ('planned', 'Storyboard Planned'),
        ('executed', 'Production Launched'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_conversations'
    )
    title = models.CharField(max_length=160)
    skill_preset = models.CharField(max_length=64, blank=True, default='general')
    aspect_ratio = models.CharField(max_length=16, default='16:9')
    character = models.ForeignKey(
        'characters.Character',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='agent_conversations'
    )
    project = models.ForeignKey(
        'projects.Project',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='agent_conversations'
    )
    clarifying_questions = models.JSONField(default=list, blank=True)
    clarifying_answers = models.JSONField(default=dict, blank=True)
    plan_snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.user.email})"


class AgentMessage(models.Model):
    """Individual turn inside a Super Agent conversation thread."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Super Agent'),
        ('system', 'System'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        AgentConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default='user')
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:50]}"


class ViralEffectTemplate(models.Model):
    """One-Tap Viral Video Effect Schema with parameterized prompt injection."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60, default='VFX')
    icon = models.CharField(max_length=16, default='✨')
    description = models.TextField(blank=True)
    prompt_template = models.TextField(help_text="Use {subject} placeholder for user subject injection")
    aspect_ratio = models.CharField(max_length=16, default='9:16')
    duration = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def render_prompt(self, subject: str) -> str:
        clean_subject = (subject or 'a cinematic hero subject').strip()
        if '{subject}' in self.prompt_template:
            return self.prompt_template.replace('{subject}', clean_subject)
        return f"{self.prompt_template} Subject: {clean_subject}"

    @classmethod
    def ensure_seeded(cls):
        """Seeds the default curated viral effects if the table is empty."""
        if cls.objects.exists():
            return cls.objects.filter(is_active=True)
        for item in DEFAULT_VIRAL_EFFECTS:
            cls.objects.get_or_create(slug=item['slug'], defaults=item)
        return cls.objects.filter(is_active=True)

