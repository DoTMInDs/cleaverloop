from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.generations.models import Generation
from apps.projects.models import Project
from apps.providers.models import AIModel
from apps.credits.services import CreditService
from apps.characters.models import Character

class HomeView(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['featured_models'] = AIModel.objects.filter(is_enabled=True, provider__is_enabled=True).order_by('-priority')[:6]
        ctx['showcase_styles'] = [
            {
                'title': 'Vintage Cartoon (1930s)',
                'category': 'Animation',
                'badge': 'Trending',
                'desc': 'Rubber hose vintage cartoon animation with nostalgic grain, bouncy movement, and classic animation character design.',
                'image': '/static/images/showcase/old_cartoon.jpg',
                'model': 'Google Veo 3.1 & Seedance',
                'prompt': 'A vintage 1930s monochrome rubber hose cartoon character rowing a wooden boat on gentle waves, whistling cheerfully.'
            },
            {
                'title': 'Unhinged Cartoon',
                'category': 'Viral Social',
                'badge': 'Viral',
                'desc': 'Wild, surreal cartoon energy with exaggerated physics, dynamic squash and stretch, designed for high social media retention.',
                'image': '/static/images/showcase/unhinged_cartoon.jpg',
                'model': 'Kling 2.6 & Fal Wan 2.1',
                'prompt': 'Surreal wacky 90s animated creature with swirling eyes jumping out of toaster with explosive animated comic sparks.'
            },
            {
                'title': 'Cozy Claymation (Everyday Life)',
                'category': 'Stop-Motion',
                'badge': 'Staff Pick',
                'desc': 'Tactile clay stop-motion scenes with warm cinematic lighting, fingerprint textures, and heartfelt miniature atmosphere.',
                'image': '/static/images/showcase/everyday_life.jpg',
                'model': 'Veo 3.1 Cinematic',
                'prompt': 'Cozy claymation couple sitting on couch in dimly lit warm apartment with rain outside, laughing at smartphones.'
            },
            {
                'title': 'Viral Neon Skeleton',
                'category': 'Cyberpunk / VFX',
                'badge': 'Social Trend',
                'desc': 'Glowing neon holographic skeletal dancers synced to upbeat club energy, dominating short-form video discovery pages.',
                'image': '/static/images/showcase/viral_skeleton.jpg',
                'model': 'MiniMax Hailuo Video-01',
                'prompt': 'Cyberpunk neon glowing holographic skeleton performing energetic viral dance in dark futuristic alleyway with rain reflections.'
            },
            {
                'title': 'Fruit Love Island',
                'category': '3D Animation',
                'badge': 'Hit Series',
                'desc': 'Whimsical 3D animated fruits living dramatic reality-TV lives in lush tropical sun-drenched beach environments.',
                'image': '/static/images/showcase/fruit_love_island.jpg',
                'model': 'Flux Ultra + Veo 3.1',
                'prompt': 'Animated anthropomorphic pineapple with sunglasses talking dramatically with cute blushing strawberry on tropical island beach.'
            },
        ]
        return ctx

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'studio/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['wallet'] = getattr(self.request, '_cached_wallet', None) or getattr(user, 'wallet', None) or CreditService.get_or_create_wallet(user)
        ctx['subscription'] = getattr(user, 'subscription', None)
        ctx['recent_generations'] = Generation.objects.filter(user=user).select_related('output_media', 'model', 'provider', 'character')[:12]
        ctx['projects'] = list(Project.objects.filter(owner=user).select_related('owner')[:6])
        ctx['projects_count'] = Project.objects.filter(owner=user).count()
        ctx['characters'] = list(Character.objects.filter(owner=user)[:6])
        ctx['characters_count'] = Character.objects.filter(owner=user).count()
        ctx['featured_models'] = AIModel.objects.filter(is_enabled=True, provider__is_enabled=True).order_by('-priority')[:6]
        ctx['trending_presets'] = [
            {
                'id': 'vintage_cartoon',
                'title': 'Vintage 1930s Cartoon',
                'icon': '🎞️',
                'tag': 'Rubber Hose',
                'type': 'video',
                'aspect': '16:9',
                'duration': 5,
                'model_name': 'Veo 3.1 & Seedance',
                'desc': 'Authentic 1930s monochrome animation with bouncy movement & film grain.',
                'image': '/static/images/showcase/old_cartoon.jpg',
                'prompt': 'Rubber hose vintage 1930s monochrome animation of a cheerful character whistling and tap dancing down a cobbled street, bouncy squash and stretch physics, authentic film grain, classic cartoon score aesthetic.',
            },
            {
                'id': 'cyberpunk_skeleton',
                'title': 'Neon Hologram Skeleton',
                'icon': '⚡',
                'tag': 'Viral VFX',
                'type': 'video',
                'aspect': '9:16',
                'duration': 5,
                'model_name': 'Kling 3.0 & Wan 2.1',
                'desc': 'Glowing electric cyan & orange holographic skeletal dancer in neon alleyway.',
                'image': '/static/images/showcase/viral_skeleton.jpg',
                'prompt': 'Glowing electric cyan and neon amber holographic skeleton performing an energetic viral dance in a dark futuristic Tokyo alley, wet rain puddle reflections, cinematic 8k photorealistic.',
            },
            {
                'id': 'claymation_cozy',
                'title': 'Cozy Stop-Motion Clay',
                'icon': '🧸',
                'tag': 'Tactile Clay',
                'type': 'video',
                'aspect': '16:9',
                'duration': 5,
                'model_name': 'Veo 3.1 Cinema',
                'desc': 'Miniature handcrafted clay characters with warm 35mm stop-motion lighting.',
                'image': '/static/images/showcase/everyday_life.jpg',
                'prompt': 'Tactile claymation miniature couple sitting on cozy sofa inside a warm apartment with rain pattering on the window, tactile fingerprint textures, warm 35mm stop-motion lighting.',
            },
            {
                'id': 'fruit_island',
                'title': 'Fruit Island Drama',
                'icon': '🌴',
                'tag': '3D Animation',
                'type': 'video',
                'aspect': '9:16',
                'duration': 5,
                'model_name': 'Flux Ultra + Veo',
                'desc': 'Anthropomorphic 3D animated fruits in dramatic tropical beach reality TV.',
                'image': '/static/images/showcase/fruit_love_island.jpg',
                'prompt': 'Animated anthropomorphic pineapple wearing sunglasses arguing dramatically with a blushing cute strawberry on a sunny tropical beach, reality TV confessional camera, Pixar 3D render.',
            },
            {
                'id': 'unhinged_cartoon',
                'title': 'Unhinged Cartoon Motion',
                'icon': '💥',
                'tag': 'Social Viral',
                'type': 'video',
                'aspect': '1:1',
                'duration': 5,
                'model_name': 'Nano Banana & Kling',
                'desc': 'Wild surreal cartoon energy with exaggerated comic squash and stretch.',
                'image': '/static/images/showcase/unhinged_cartoon.jpg',
                'prompt': 'Hyperactive wacky 90s animated creature with swirling eyes popping out of a chrome toaster with dynamic comic sparks, exaggerated squash and stretch, vivid saturated colors.',
            },
            {
                'id': 'cinematic_portrait',
                'title': 'Cinematic Neon Portrait',
                'icon': '📸',
                'tag': 'Photoreal 4K',
                'type': 'image',
                'aspect': '1:1',
                'duration': 0,
                'model_name': 'Nano Banana 2',
                'desc': 'Editorial close-up with rain droplets, shallow depth of field & anamorphic flare.',
                'image': '/static/images/showcase/everyday_life.jpg',
                'prompt': 'Close-up cinematic editorial portrait of an intrepid explorer in a neon-lit cyberpunk market, raindrops on jacket, shallow depth of field, anamorphic bokeh, 8k masterpiece.',
            },
        ]
        return ctx

class CreateStudioView(LoginRequiredMixin, TemplateView):
    template_name = 'studio/create.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['wallet'] = getattr(self.request, '_cached_wallet', None) or getattr(user, 'wallet', None) or CreditService.get_or_create_wallet(user)
        ctx['image_models'] = AIModel.objects.filter(modality='image', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        ctx['video_models'] = AIModel.objects.filter(modality='video', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        ctx['characters'] = Character.objects.filter(owner=user)
        ctx['projects'] = Project.objects.filter(owner=user)
        ctx['recent_generations'] = Generation.objects.filter(user=user).select_related('output_media', 'model', 'provider')[:4]
        ctx['trending_presets'] = [
            {
                'id': 'vintage_cartoon',
                'title': 'Vintage 1930s Cartoon',
                'icon': '🎞️',
                'tag': 'Rubber Hose',
                'type': 'video',
                'aspect': '16:9',
                'duration': 5,
                'prompt': 'Rubber hose vintage 1930s monochrome animation of a cheerful character whistling and tap dancing down a cobbled street, bouncy squash and stretch physics, authentic film grain, classic cartoon score aesthetic.',
            },
            {
                'id': 'cyberpunk_skeleton',
                'title': 'Neon Hologram Skeleton',
                'icon': '⚡',
                'tag': 'Viral VFX',
                'type': 'video',
                'aspect': '9:16',
                'duration': 5,
                'prompt': 'Glowing electric cyan and neon amber holographic skeleton performing an energetic viral dance in a dark futuristic Tokyo alley, wet rain puddle reflections, cinematic 8k photorealistic.',
            },
            {
                'id': 'claymation_cozy',
                'title': 'Cozy Stop-Motion Clay',
                'icon': '🧸',
                'tag': 'Tactile Stop-Mo',
                'type': 'video',
                'aspect': '16:9',
                'duration': 5,
                'prompt': 'Tactile claymation miniature couple sitting on cozy sofa inside a warm apartment with rain pattering on the window, tactile fingerprint textures, warm 35mm stop-motion lighting.',
            },
            {
                'id': 'fruit_island',
                'title': 'Fruit Island Drama',
                'icon': '🌴',
                'tag': '3D Animation',
                'type': 'video',
                'aspect': '9:16',
                'duration': 5,
                'prompt': 'Animated anthropomorphic pineapple wearing sunglasses arguing dramatically with a blushing cute strawberry on a sunny tropical beach, reality TV confessional camera, Pixar 3D render.',
            },
            {
                'id': 'unhinged_cartoon',
                'title': 'Unhinged Cartoon Motion',
                'icon': '💥',
                'tag': 'Social Viral',
                'type': 'video',
                'aspect': '1:1',
                'duration': 5,
                'prompt': 'Hyperactive wacky 90s animated creature with swirling eyes popping out of a chrome toaster with dynamic comic sparks, exaggerated squash and stretch, vivid saturated colors.',
            },
            {
                'id': 'cinematic_portrait',
                'title': 'Cinematic Neon Portrait',
                'icon': '📸',
                'tag': 'Photoreal Image',
                'type': 'image',
                'aspect': '1:1',
                'duration': 0,
                'prompt': 'Close-up cinematic editorial portrait of an intrepid explorer in a neon-lit cyberpunk market, raindrops on jacket, shallow depth of field, anamorphic bokeh, 8k masterpiece.',
            },
        ]
        return ctx

class ExploreView(TemplateView):
    """Community Explore & Showcase feed featuring dynamically generated creations from all users."""
    template_name = 'studio/explore.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user if self.request.user.is_authenticated else None
        
        # 1. Dynamically query completed generations from ALL users
        db_gens = Generation.objects.filter(
            status='completed',
            output_media__isnull=False
        ).select_related('output_media', 'model', 'provider', 'user', 'character', 'project').order_by('-created_at')[:40]

        ctx['db_generations'] = db_gens

        dynamic_user_items = []
        for gen in db_gens:
            if not gen.output_media:
                continue
            
            media_url = gen.output_media.file.url if gen.output_media.file else (gen.output_media.url or '')
            if not media_url:
                continue

            username = gen.user.username if gen.user and gen.user.username else 'creator'
            creator_name = f"@{username}"
            avatar_letter = username[0].upper() if username else 'C'

            # Classify style / category based on prompt keywords
            p_low = gen.prompt.lower()
            if 'clay' in p_low or 'stop-motion' in p_low:
                category = 'Stop-Motion Clay'
            elif 'cartoon' in p_low or 'anime' in p_low or 'vintage' in p_low or 'rubber hose' in p_low:
                category = 'Animation'
            elif 'portrait' in p_low or 'face' in p_low or 'ugc' in p_low or 'vlog' in p_low or 'beach' in p_low:
                category = 'Viral Social VFX'
            elif 'fantasy' in p_low or 'knight' in p_low or 'dragon' in p_low or 'magic' in p_low:
                category = 'Dark Fantasy'
            elif '3d' in p_low or 'pixar' in p_low:
                category = '3D Animation'
            else:
                category = 'Cyberpunk / Sci-Fi'

            # Title from project name or prompt snippet
            if gen.project and gen.project.name:
                title = gen.project.name
            else:
                # First clean sentence or 40 characters
                clean_p = gen.prompt.split('.')[0].strip()
                title = clean_p[:45] + ('...' if len(clean_p) > 45 else '')

            # Like calculation from seed or id
            hash_val = abs(hash(str(gen.id)))
            likes_count = (hash_val % 3500) + 420

            dynamic_user_items.append({
                'id': str(gen.id),
                'title': title or 'AI Generation',
                'creator': creator_name,
                'avatar_letter': avatar_letter,
                'type': gen.generation_type or 'video',
                'media_url': media_url,
                'model_name': gen.model.display_name if gen.model else 'AI Engine',
                'model_badge': gen.model.display_name if gen.model else 'Veo Cinema',
                'aspect_ratio': gen.aspect_ratio or '16:9',
                'duration': gen.duration or 0,
                'category': category,
                'likes': likes_count,
                'is_staff_pick': bool(gen.character is not None or (gen.duration and gen.duration >= 10)),
                'character_name': gen.character.name if gen.character else '',
                'prompt': gen.prompt,
                'negative_prompt': gen.negative_prompt or '',
                'seed': gen.seed or (hash_val % 999999999),
                'is_user_generated': True
            })

        # Curated community showcase items fallback/supplement
        curated_showcase = [
            {
                'id': 'exp-1',
                'title': 'Night Forest Campfire Clay Story',
                'creator': '@clay_tales',
                'avatar_letter': 'C',
                'type': 'video',
                'media_url': '/static/images/showcase/everyday_life.jpg',
                'model_name': 'Veo 3.1 Cinematic',
                'model_badge': 'Tactile Stop-Mo',
                'aspect_ratio': '9:16',
                'duration': 5,
                'category': 'Stop-Motion Clay',
                'likes': 1920,
                'is_staff_pick': True,
                'character_name': 'Leo & Mia',
                'prompt': 'Charming stop-motion claymation miniature of two adventurous clay children sitting beside a glowing campfire in a dark pine forest under starry night sky, warm firelight flicker on handcrafted clay coats.',
                'negative_prompt': 'digital 3d, smooth plastic, CGI, oversaturated',
                'seed': 120938491
            },
            {
                'id': 'exp-2',
                'title': 'Summer Beach Skincare UGC Reel',
                'creator': '@chloe_creatives',
                'avatar_letter': 'C',
                'type': 'video',
                'media_url': '/media/uploads/1/reference/55ec271bc3ba.jpg',
                'model_name': 'Kling 3.0 Ultra',
                'model_badge': 'Photoreal UGC',
                'aspect_ratio': '9:16',
                'duration': 15,
                'category': 'Viral Social VFX',
                'likes': 3420,
                'is_staff_pick': True,
                'character_name': 'Chloe Vance',
                'prompt': 'A joyful creator holding up a luxury skincare lotion tube under bright Mediterranean sunshine at a coastal beach resort, beaming natural smile, sparkling sea bokeh in background, authentic 4k smartphone UGC style.',
                'negative_prompt': 'bad lighting, blurred product, distorted fingers',
                'seed': 884910293
            },
            {
                'id': 'exp-3',
                'title': 'Midnight Ethereal Winged Gliders',
                'creator': '@sky_alchemist',
                'avatar_letter': 'S',
                'type': 'video',
                'media_url': '/media/uploads/1/reference/0b2bd9ae33ab.png',
                'model_name': 'Google Veo 3.1',
                'model_badge': 'Veo 3.1 Cinema',
                'aspect_ratio': '16:9',
                'duration': 10,
                'category': 'Cyberpunk / Sci-Fi',
                'likes': 2890,
                'is_staff_pick': True,
                'character_name': 'Zephyr Wing',
                'prompt': 'Cinematic shot of celestial aerial adventurers with glowing crystalline fairy wings soaring through a stormy twilight sky anchored by heavy iron clockwork pulleys, volumetric lightning illumination, magical particles.',
                'negative_prompt': 'blurry, flat lighting, artifacts, 2d cartoon',
                'seed': 384910294
            },
            {
                'id': 'exp-4',
                'title': 'Street Phone Call Drama',
                'creator': '@urban_cinema',
                'avatar_letter': 'U',
                'type': 'video',
                'media_url': '/media/uploads/1/reference/1a541e74d169.png',
                'model_name': 'Kling 3.0 Ultra',
                'model_badge': 'Commercial Pro',
                'aspect_ratio': '9:16',
                'duration': 8,
                'category': 'Viral Social VFX',
                'likes': 1680,
                'is_staff_pick': False,
                'character_name': 'Marcus & Elena',
                'prompt': 'Cinematic tracking shot along a sunlit New York brownstone sidewalk as two executives in modern suits have an animated conversation on a smartphone, soft golden hour lens flares, anamorphic bokeh.',
                'negative_prompt': 'lowres, grainy, distorted facial features',
                'seed': 748192048
            },
            {
                'id': 'exp-5',
                'title': 'Urban Street Energy Drink Commercial',
                'creator': '@beast_mode',
                'avatar_letter': 'B',
                'type': 'video',
                'media_url': '/media/uploads/1/reference/33b3f2fc7152.png',
                'model_name': 'Google Veo 3.1',
                'model_badge': 'Commercial Pro',
                'aspect_ratio': '9:16',
                'duration': 10,
                'category': 'Viral Social VFX',
                'likes': 2450,
                'is_staff_pick': False,
                'character_name': 'Kenji Sato',
                'prompt': 'Dynamic handheld camera shot of a stylish young creator in a yellow athletic jersey holding up a sleek glowing purple energy drink can in downtown city street at golden hour, confident smile, cinematic motion blur.',
                'negative_prompt': 'low quality, blurry label, oversaturated face',
                'seed': 662910481
            },
            {
                'id': 'exp-6',
                'title': 'Medieval Tavern Knight Victory Toast',
                'creator': '@valiant_lore',
                'avatar_letter': 'V',
                'type': 'video',
                'media_url': '/media/uploads/1/reference/358ecb8a0783.png',
                'model_name': 'Flux 1.1 Pro Ultra',
                'model_badge': 'Photoreal 8K',
                'aspect_ratio': '16:9',
                'duration': 0,
                'category': 'Dark Fantasy',
                'likes': 3100,
                'is_staff_pick': True,
                'character_name': 'Sir Galahad',
                'prompt': 'Atmospheric fantasy anime scene of medieval knights in royal blue tunics and steel armor raising wooden tankards of ale in a cozy candlelit tavern, royal eagle banner in background, hearty laughter, warm amber lighting.',
                'negative_prompt': '3D CGI, low quality, deformed hands',
                'seed': 991823011
            },
            {
                'id': 'exp-7',
                'title': '30s Cyberpunk Autonomous EV Infiltrator',
                'creator': '@neon_director',
                'avatar_letter': 'N',
                'type': 'video',
                'media_url': '/media/uploads/1/reference/3c0696f309a1.png',
                'model_name': 'Google Veo 3.1',
                'model_badge': 'Veo 3.1 Cinema',
                'aspect_ratio': '16:9',
                'duration': 10,
                'category': 'Cyberpunk / Sci-Fi',
                'likes': 4420,
                'is_staff_pick': True,
                'character_name': 'Kaelen Vance',
                'prompt': 'An autonomous electric hypercar with FLASHLOOP.AI livery gliding through a rainy futuristic neo-Tokyo at midnight, rain droplets beading on aerodynamic carbon fiber, red LED taillights glowing, accelerating into a misty tunnel.',
                'negative_prompt': 'blurry, low resolution, artifacts, distorted geometry, cartoonish',
                'seed': 489218491
            },
            {
                'id': 'exp-8',
                'title': 'Anime Electric Katana Clash',
                'creator': '@sakura_blade',
                'avatar_letter': 'K',
                'type': 'video',
                'media_url': '/media/uploads/1/reference/3d638a185fab.png',
                'model_name': 'Seedance 2.5 Pro',
                'model_badge': 'Anime Action',
                'aspect_ratio': '16:9',
                'duration': 5,
                'category': 'Cyberpunk / Sci-Fi',
                'likes': 4200,
                'is_staff_pick': True,
                'character_name': 'Ren Kurogane',
                'prompt': 'Extreme dynamic close-up anime shot of an electric katana blade reflecting glowing cyan lightning sparks across a warrior\'s determined eyes, shattering rock particles flying past camera in slow-motion, Ufotable studio aesthetic.',
                'negative_prompt': '3D CGI, blurry lines, low framerate',
                'seed': 449102941
            },
            {
                'id': 'exp-9',
                'title': 'Poolside Villa Claymation Holiday',
                'creator': '@clay_paradise',
                'avatar_letter': 'P',
                'type': 'video',
                'media_url': '/static/images/showcase/fruit_love_island.jpg',
                'model_name': 'Veo 3.1 Cinematic',
                'model_badge': 'Tactile Stop-Mo',
                'aspect_ratio': '1:1',
                'duration': 5,
                'category': 'Stop-Motion Clay',
                'likes': 2190,
                'is_staff_pick': False,
                'character_name': 'Barnaby & Lola',
                'prompt': 'Charming claymation stop-motion scene of a relaxing couple lounging by a luxury turquoise swimming pool outside a modern white villa, eating grapes under swaying palm trees, handcrafted clay textures, bright warm sunlight.',
                'negative_prompt': 'photoreal human, flat 2d, digital rendering',
                'seed': 193849102
            },
            {
                'id': 'exp-10',
                'title': 'Nova Pop Hologram Candy Snack',
                'creator': '@candy_wave',
                'avatar_letter': 'N',
                'type': 'video',
                'media_url': '/media/uploads/1/reference/42cbce215816.png',
                'model_name': 'Kling 3.0 Ultra',
                'model_badge': 'Photoreal UGC',
                'aspect_ratio': '9:16',
                'duration': 10,
                'category': 'Viral Social VFX',
                'likes': 3820,
                'is_staff_pick': True,
                'character_name': 'Yuki Star',
                'prompt': 'Close-up UGC video of a trendy girl with blue hair in a cap holding up a colorful purple Nova Pop candy pouch under sparkling crystal chandelier lights, playful expression, glowing neon aesthetic.',
                'negative_prompt': 'blurry pouch, distorted eyes, bad colors',
                'seed': 558192049
            },
            {
                'id': 'exp-11',
                'title': '1930s Rubber Hose Cartoon Bakery',
                'creator': '@retro_toon',
                'avatar_letter': 'R',
                'type': 'video',
                'media_url': '/static/images/showcase/old_cartoon.jpg',
                'model_name': 'Seedance 2.5 Pro',
                'model_badge': 'Rubber Hose',
                'aspect_ratio': '16:9',
                'duration': 5,
                'category': '1930s Animation',
                'likes': 1750,
                'is_staff_pick': True,
                'character_name': 'Barnaby Baker',
                'prompt': 'Classic 1930s black-and-white rubber hose animation short. A cheerful cartoon baker in oversized gloves is chased around a vintage kitchen by dancing cupcakes, bouncy squash-and-stretch physics, authentic grain.',
                'negative_prompt': 'modern 3d, colors, HD sharp CGI, realistic human',
                'seed': 338192049
            },
            {
                'id': 'exp-12',
                'title': 'Neon Holographic Skeleton Dance',
                'creator': '@vfx_alchemist',
                'avatar_letter': 'V',
                'type': 'video',
                'media_url': '/static/images/showcase/viral_skeleton.jpg',
                'model_name': 'Kling 3.0 Ultra',
                'model_badge': 'Physics Engine',
                'aspect_ratio': '9:16',
                'duration': 15,
                'category': 'Viral Social VFX',
                'likes': 5840,
                'is_staff_pick': True,
                'character_name': 'Maya Lin',
                'prompt': 'A high-energy glowing electric cyan and orange holographic skeletal dancer performing synchronized choreography in an abandoned cyberpunk subway terminal, volumetric laser strobe lighting and wet puddle reflections.',
                'negative_prompt': 'static camera, jitter, watermark, dull lighting',
                'seed': 774892019
            }
        ]

        # Combine dynamic user creations with curated items (putting user creations first)
        combined_showcase = dynamic_user_items + [item for item in curated_showcase if not any(u.get('id') == item.get('id') for u in dynamic_user_items)]
        ctx['community_showcase'] = combined_showcase
        return ctx


