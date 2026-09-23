from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.generations.models import Generation
from apps.projects.models import Project
from apps.providers.models import AIModel
from apps.credits.services import CreditService
from apps.characters.models import Character
from apps.generations.tasks import reap_stale_generations

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
        reap_stale_generations(user=user, timeout_minutes=15)
        ctx['wallet'] = getattr(self.request, '_cached_wallet', None) or getattr(user, 'wallet', None) or CreditService.get_or_create_wallet(user)
        ctx['subscription'] = getattr(user, 'subscription', None)
        ctx['recent_generations'] = Generation.objects.filter(user=user, parent_generation__isnull=True).select_related('output_media', 'model', 'provider', 'character')[:12]
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
        reap_stale_generations(user=user, timeout_minutes=15)
        ctx['wallet'] = getattr(self.request, '_cached_wallet', None) or getattr(user, 'wallet', None) or CreditService.get_or_create_wallet(user)
        ctx['image_models'] = AIModel.objects.filter(modality='image', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        ctx['video_models'] = AIModel.objects.filter(modality='video', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        ctx['audio_models'] = AIModel.objects.filter(modality='audio', is_enabled=True, provider__is_enabled=True).order_by('-priority')
        from apps.providers.adapters.elevenlabs import ElevenLabsProvider
        ctx['available_voices'] = ElevenLabsProvider.get_available_voices()
        ctx['characters'] = Character.objects.filter(owner=user)
        ctx['projects'] = Project.objects.filter(owner=user)
        ctx['recent_generations'] = Generation.objects.filter(user=user, parent_generation__isnull=True).select_related('output_media', 'model', 'provider')[:12]
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

        # 1. Query real completed generations with output media from ALL platform users
        db_gens = Generation.objects.filter(
            status='completed',
            output_media__isnull=False
        ).select_related('output_media', 'model', 'provider', 'user', 'character', 'project').order_by('-created_at')[:80]

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

            p_low = gen.prompt.lower()
            
            # Team Classification (Marketing Teams, Agencies, Creators)
            if any(w in p_low for w in ['ad', 'ugc', 'product', 'marketing', 'promo', 'ecommerce', 'retail', 'sale', 'cream', 'skincare', 'energy drink', 'snack', 'certificate', 'interview']):
                team = 'marketing'
            elif any(w in p_low for w in ['commercial', 'brand', 'luxury', 'car', 'hypercar', 'amg', 'cinematic', 'film', 'trailer', 'director', '8k', '4k', 'anamorphic', 'corporate']):
                team = 'agencies'
            else:
                team = 'creators'

            # Format Classification
            if any(w in p_low for w in ['ugc', 'review', 'selfie', 'phone', 'cream', 'skincare', 'walk']):
                produce_format = 'ugc_ads'
            elif any(w in p_low for w in ['drama', 'suspense', 'cliffhanger', 'episode', 'talking', 'dialogue', 'story']):
                produce_format = 'micro_drama'
            elif any(w in p_low for w in ['explainer', 'tutorial', 'breakdown', 'concept', 'guide', 'learn']):
                produce_format = 'explainer_video'
            elif any(w in p_low for w in ['short film', 'film', 'cinema', 'movie', 'narrative', 'quest']):
                produce_format = 'short_film'
            elif any(w in p_low for w in ['social', 'tiktok', 'reel', 'dance', 'viral', 'street', 'accra']):
                produce_format = 'social_content'
            elif gen.generation_type == 'image' or any(w in p_low for w in ['photo', 'portrait', 'still', 'billboard']):
                produce_format = 'brand_images'
            else:
                produce_format = 'brand_video'

            # Genre category
            if 'clay' in p_low or 'stop-motion' in p_low:
                category = 'Claymation'
            elif 'anime' in p_low or 'sports' in p_low or 'katana' in p_low:
                category = 'Sports Anime'
            elif 'stickman' in p_low or 'cave' in p_low or 'trojan' in p_low:
                category = 'Stickman Cartoon'
            elif 'watercolor' in p_low or 'parchment' in p_low:
                category = 'Watercolor'
            elif 'paper' in p_low or 'collage' in p_low:
                category = 'Paper Collage'
            elif 'hand drawn' in p_low or 'sketch' in p_low:
                category = 'Hand Drawn'
            elif 'ugc' in p_low or 'ad' in p_low or 'product' in p_low:
                category = 'UGC & Social Ads'
            elif 'commercial' in p_low or 'brand' in p_low or 'luxury' in p_low:
                category = 'Brand Commercials'
            else:
                category = 'Micro Drama'

            # Title
            if gen.project and gen.project.name:
                title = gen.project.name
            else:
                clean_p = gen.prompt.split('.')[0].strip()
                title = clean_p[:45] + ('...' if len(clean_p) > 45 else '')

            hash_val = abs(hash(str(gen.id)))
            likes_count = (hash_val % 4200) + 380

            dynamic_user_items.append({
                'id': str(gen.id),
                'title': title or 'Community Creation',
                'creator': creator_name,
                'avatar_letter': avatar_letter,
                'type': gen.generation_type or 'video',
                'media_url': media_url,
                'model_name': gen.model.display_name if gen.model else 'AI Engine',
                'model_badge': gen.model.display_name if gen.model else 'Veo Cinema',
                'aspect_ratio': gen.aspect_ratio or '16:9',
                'duration': gen.duration or 5,
                'category': category,
                'team': team,
                'produce_format': produce_format,
                'likes': likes_count,
                'is_staff_pick': bool(gen.character is not None or (gen.duration and gen.duration >= 10)),
                'character_name': gen.character.name if gen.character else '',
                'prompt': gen.prompt,
                'negative_prompt': gen.negative_prompt or '',
                'seed': gen.seed or (hash_val % 999999999),
                'is_user_generated': True
            })

        # 2. Produce Formats for Section 1 ("SEE WHAT YOU CAN PRODUCE ON FLASHLOOP")
        first_video_url = next((u['media_url'] for u in dynamic_user_items if u['type'] == 'video'), '/static/images/showcase/old_cartoon.jpg')
        first_ugc_url = next((u['media_url'] for u in dynamic_user_items if u['produce_format'] == 'ugc_ads'), first_video_url)
        first_drama_url = next((u['media_url'] for u in dynamic_user_items if u['produce_format'] == 'micro_drama'), first_video_url)

        ctx['produce_formats'] = [
            {
                'id': 'ugc_ads',
                'label': 'UGC ADS',
                'heading': 'UGC ADS',
                'desc': 'High-converting creator testimonials and product unboxings that blend seamlessly into social feeds.',
                'media_url': first_ugc_url,
                'media_type': 'video' if first_ugc_url.endswith(('.mp4', '.mov', '.webm')) else 'image',
                'create_prompt': 'Authentic smartphone selfie UGC creator unboxing and reviewing product with natural lighting',
                'aspect_ratio': '9:16',
            },
            {
                'id': 'micro_drama',
                'label': 'MICRO DRAMA',
                'heading': 'MICRO DRAMA',
                'desc': 'High-stakes episodic cliffhangers and character face-offs designed for hyper-retention vertical streaming.',
                'media_url': first_drama_url,
                'media_type': 'video' if first_drama_url.endswith(('.mp4', '.mov', '.webm')) else 'image',
                'create_prompt': 'Intense dramatic confrontation between two characters, emotional close-up, cinematic lighting, 9:16 vertical',
                'aspect_ratio': '9:16',
            },
            {
                'id': 'explainer_video',
                'label': 'EXPLAINER VIDEO',
                'heading': 'EXPLAINER VIDEO',
                'desc': 'Crisp visual breakdowns and kinetic motion concepts that make complex products intuitive in seconds.',
                'media_url': first_video_url,
                'media_type': 'video' if first_video_url.endswith(('.mp4', '.mov', '.webm')) else 'image',
                'create_prompt': 'Dynamic motion explainer video with sleek 3D holographic UI interfaces, clean modern camera motion',
                'aspect_ratio': '16:9',
            },
            {
                'id': 'short_film',
                'label': 'SHORT FILM',
                'heading': 'SHORT FILM',
                'desc': 'Festival-grade cinematic short stories with persistent cast characters and director-level camera moves.',
                'media_url': first_video_url,
                'media_type': 'video' if first_video_url.endswith(('.mp4', '.mov', '.webm')) else 'image',
                'create_prompt': 'Cinematic narrative short film, slow atmospheric tracking shot at dawn, 35mm film grain, 4k master',
                'aspect_ratio': '16:9',
            },
            {
                'id': 'social_content',
                'label': 'SOCIAL CONTENT',
                'heading': 'SOCIAL CONTENT',
                'desc': 'Daily viral reels, memes, and trend-jacking hooks generated in seconds to keep your channels always ahead.',
                'media_url': first_video_url,
                'media_type': 'video' if first_video_url.endswith(('.mp4', '.mov', '.webm')) else 'image',
                'create_prompt': 'Fast-paced viral social video with dynamic camera cuts, eye-catching visual hooks, trending aesthetic',
                'aspect_ratio': '9:16',
            },
            {
                'id': 'brand_images',
                'label': 'BRAND IMAGES',
                'heading': 'BRAND IMAGES',
                'desc': 'Studio-grade key art, luxury lookbook portraits, and hyper-detailed product renders with perfect zero-drift lighting.',
                'media_url': '/media/characters/avatars/marcus_vance_fullbody.jpg',
                'media_type': 'image',
                'create_prompt': 'Full-length luxury fashion editorial portrait in a minimalist architectural studio, cinematic softbox lighting, 8k masterpiece',
                'aspect_ratio': '9:16',
            },
            {
                'id': 'brand_video',
                'label': 'BRAND VIDEO',
                'heading': 'BRAND VIDEO',
                'desc': 'On-brand spots that look like an agency built them, minus the agency.',
                'media_url': '/static/images/showcase/brand_video_car.jpg',
                'media_type': 'image',
                'create_prompt': 'Luxury automotive commercial tracking a sleek matte black sports coupe through rain-slicked city streets at night, glowing red taillights, cinematic 8k',
                'aspect_ratio': '16:9',
            }
        ]

        # 3. Who It's For Segments (Screenshot 2)
        ctx['who_its_for_segments'] = [
            {
                'id': 'marketing',
                'title': 'Marketing Teams',
                'icon_url': '/static/images/showcase/icon_marketing.jpg',
                'description': 'Fill the content calendar with formats proven to pull views. No crew, no shoot days, no edit bay. Ship daily, learn fast.',
                'badge_color': 'emerald',
                'count': sum(1 for u in dynamic_user_items if u['team'] == 'marketing')
            },
            {
                'id': 'agencies',
                'title': 'Agencies',
                'icon_url': '/static/images/showcase/icon_agency.jpg',
                'description': 'Turn trend jacking around the same day. Pitch and deliver client work built on formats already generating millions of views.',
                'badge_color': 'amber',
                'count': sum(1 for u in dynamic_user_items if u['team'] == 'agencies')
            },
            {
                'id': 'creators',
                'title': 'Creators',
                'icon_url': '/static/images/showcase/icon_creator.jpg',
                'description': 'Ride every wave first. New viral formats land constantly, so your channel never misses a trend worth posting.',
                'badge_color': 'rose',
                'count': sum(1 for u in dynamic_user_items if u['team'] == 'creators')
            }
        ]

        # 4. Top Trends (Screenshot 4)
        ctx['top_trends'] = [
            {
                'id': 'sports_anime_1',
                'category': 'sports_anime',
                'label': 'Sports Anime',
                'image_url': '/static/images/showcase/unhinged_cartoon.jpg',
                'prompt': 'High-energy sports anime animation of players in royal blue uniforms inside a modern locker room, intense expressions, dynamic lighting',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'sports_anime_2',
                'category': 'sports_anime',
                'label': 'Sports Anime',
                'image_url': '/media/characters/avatars/marcus_vance_walking.jpg',
                'prompt': 'Dynamic sports anime warriors colliding with glowing cyan and blue energy blades, electrifying sparks flying, intense rivalry, anime speed lines',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'sports_anime_3',
                'category': 'sports_anime',
                'label': 'Sports Anime',
                'image_url': '/static/images/showcase/unhinged_cartoon.jpg',
                'prompt': 'Emotional anime character in pouring rain, dramatic tears streaming down cheeks, golden collar insignia, cinematic lighting, masterpiece',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'stickman_cartoon_1',
                'category': 'stickman_cartoon',
                'label': 'Stickman Cartoon',
                'image_url': '/static/images/showcase/old_cartoon.jpg',
                'prompt': 'Whimsical storybook stickman cartoon carving ancient symbols into seaside cliff cave, textured paper storybook illustration',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'stickman_cartoon_2',
                'category': 'stickman_cartoon',
                'label': 'Stickman Cartoon',
                'image_url': '/static/images/showcase/old_cartoon.jpg',
                'prompt': 'Minimalist stickman cartoon astronomer peering through a tall brass wooden telescope at starry night sky, cozy storybook atmosphere',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'stickman_cartoon_3',
                'category': 'stickman_cartoon',
                'label': 'Stickman Cartoon',
                'image_url': '/static/images/showcase/old_cartoon.jpg',
                'prompt': 'Whimsical cartoon soldiers climbing out of a wooden Trojan horse outside stone fortress walls, charming storybook line art style',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'claymation_1',
                'category': 'claymation',
                'label': 'Claymation',
                'image_url': '/static/images/showcase/everyday_life.jpg',
                'prompt': 'Tactile stop-motion claymation mother gently patting a swaddled clay baby in a wooden crib, warm candlelight, clay fingerprint textures, 35mm lighting',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'claymation_2',
                'category': 'claymation',
                'label': 'Claymation',
                'image_url': '/static/images/showcase/everyday_life.jpg',
                'prompt': 'Stop-motion claymation passengers riding a vintage green city bus through rain-streaked windows, nostalgic tactile characters, warm film lighting',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'claymation_3',
                'category': 'claymation',
                'label': 'Claymation',
                'image_url': '/static/images/showcase/everyday_life.jpg',
                'prompt': 'Charming bearded claymation scholar at a wooden library desk examining miniature planet through brass telescope, warm oil lamp glow',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'watercolor_1',
                'category': 'watercolor',
                'label': 'Watercolor',
                'image_url': '/static/images/showcase/fruit_love_island.jpg',
                'prompt': 'Delicate scientific watercolor illustration of hand pointing to circular petri dish on vintage aged parchment paper, antique manuscript look',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'watercolor_2',
                'category': 'watercolor',
                'label': 'Watercolor',
                'image_url': '/static/images/showcase/fruit_love_island.jpg',
                'prompt': 'Artistic antique watercolor world map with muted grey and blue continents on textured parchment, vintage explorer cartography',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'watercolor_3',
                'category': 'watercolor',
                'label': 'Watercolor',
                'image_url': '/static/images/showcase/fruit_love_island.jpg',
                'prompt': 'Peaceful soft watercolor painting of solitary white lighthouse on rocky grassy coastline overlooking calm ocean water, gentle wash tones',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'paper_collage_1',
                'category': 'paper_collage',
                'label': 'Paper Collage',
                'image_url': '/static/images/showcase/viral_skeleton.jpg',
                'prompt': 'Cutout layered paper craft illustration of man speaking into vintage telegraph microphone communicating with child below, split-level room',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'paper_collage_2',
                'category': 'paper_collage',
                'label': 'Paper Collage',
                'image_url': '/static/images/showcase/viral_skeleton.jpg',
                'prompt': 'Handcrafted paper collage of boy looking curiously at wooden pantry shelves filled with paper cutout bottles, boxes, and jars',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'paper_collage_3',
                'category': 'paper_collage',
                'label': 'Paper Collage',
                'image_url': '/static/images/showcase/viral_skeleton.jpg',
                'prompt': 'Layered 3D paper collage scene of students seated at wooden school desks writing in notebooks as another enters blue doorway, tactile shadows',
                'aspect_ratio': '9:16'
            },
            {
                'id': 'hand_drawn_1',
                'category': 'hand_drawn',
                'label': 'Hand Drawn',
                'image_url': '/static/images/showcase/old_cartoon.jpg',
                'prompt': 'Fine black-and-white technical pencil and ink architectural sketch of office desk with modern desktop printer and price tags hanging, cross-hatching',
                'aspect_ratio': '9:16'
            }
        ]

        # 5. Categorized Carousels Data
        ctx['carousel_categories'] = [
            {
                'id': 'all',
                'label': '🔥 All Trending',
                'items': dynamic_user_items[:20]
            },
            {
                'id': 'ugc_ads',
                'label': '📱 UGC & Social Ads',
                'items': [u for u in dynamic_user_items if u['produce_format'] == 'ugc_ads' or u['team'] == 'marketing'][:15]
            },
            {
                'id': 'micro_drama',
                'label': '🎭 Micro Drama & Cinema',
                'items': [u for u in dynamic_user_items if u['produce_format'] in ('micro_drama', 'short_film') or u['team'] == 'agencies'][:15]
            },
            {
                'id': 'brand_commercials',
                'label': '✨ Brand Commercials',
                'items': [u for u in dynamic_user_items if u['produce_format'] in ('brand_video', 'brand_images') or u['team'] == 'agencies'][:15]
            },
            {
                'id': 'animation_vfx',
                'label': '⚡ Animation & VFX',
                'items': [u for u in dynamic_user_items if u['category'] in ('Claymation', 'Sports Anime', 'Stickman Cartoon', 'Watercolor', 'Paper Collage', 'Hand Drawn') or u['team'] == 'creators'][:15]
            }
        ]

        ctx['community_showcase'] = dynamic_user_items
        return ctx


