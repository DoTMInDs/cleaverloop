import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from apps.providers.models import AIProviderConfig, AIModel
from apps.billing.models import SubscriptionPlan
from apps.credits.models import CreditWallet

def seed_all():
    print("--- Seeding Google AI Provider & Models ---")
    provider, _ = AIProviderConfig.objects.update_or_create(
        slug='google',
        defaults={
            'name': 'Google Gemini & Veo (Unified Engine)',
            'is_enabled': True,
            'health_status': 'healthy',
            'api_key_env_var': 'GEMINI_API_KEY',
        }
    )

    models_data = [
        {
            'model_id': 'nano-banana-2-lite',
            'display_name': 'Nano Banana 2 Lite',
            'modality': 'image',
            'credit_cost_fixed': 250,
            'credit_cost_per_second': 0,
            'max_duration': 0,
            'priority': 90,
            'is_premium': False,
            'supports_image_reference': True,
            'capabilities': ['t2i', 'fast_draft', '1k'],
            'supported_aspect_ratios': ['16:9', '9:16', '1:1', '21:9'],
        },
        {
            'model_id': 'nano-banana-2',
            'display_name': 'Nano Banana 2 (Standard)',
            'modality': 'image',
            'credit_cost_fixed': 750,
            'credit_cost_per_second': 0,
            'max_duration': 0,
            'priority': 100,
            'is_premium': False,
            'supports_image_reference': True,
            'capabilities': ['t2i', 'photoreal', '2k'],
            'supported_aspect_ratios': ['16:9', '9:16', '1:1', '21:9'],
        },
        {
            'model_id': 'nano-banana-pro',
            'display_name': 'Nano Banana Pro',
            'modality': 'image',
            'credit_cost_fixed': 1500,
            'credit_cost_per_second': 0,
            'max_duration': 0,
            'priority': 80,
            'is_premium': True,
            'supports_image_reference': True,
            'capabilities': ['t2i', '4k', 'masterpiece', 'hdr'],
            'supported_aspect_ratios': ['16:9', '9:16', '1:1', '21:9'],
        },
        {
            'model_id': 'veo-3.1-lite',
            'display_name': 'Veo 3.1 Lite (Draft Motion)',
            'modality': 'video',
            'credit_cost_fixed': 0,
            'credit_cost_per_second': 2000,
            'max_duration': 10,
            'priority': 85,
            'is_premium': False,
            'supports_audio': True,
            'supports_image_reference': True,
            'capabilities': ['t2v', 'i2v', 'audio', 'fast_render'],
            'supported_aspect_ratios': ['16:9', '9:16', '1:1', '21:9'],
        },
        {
            'model_id': 'veo-3.1-fast',
            'display_name': 'Veo 3.1 Fast (Standard + Native Audio)',
            'modality': 'video',
            'credit_cost_fixed': 0,
            'credit_cost_per_second': 4400,
            'max_duration': 10,
            'priority': 100,
            'is_premium': False,
            'supports_audio': True,
            'supports_image_reference': True,
            'capabilities': ['t2v', 'i2v', 'audio', 'cinematic_motion', 'native_sound'],
            'supported_aspect_ratios': ['16:9', '9:16', '1:1', '21:9'],
        },
        {
            'model_id': 'veo-3.1-standard',
            'display_name': 'Veo 3.1 Standard (Cinema Master + Native Audio)',
            'modality': 'video',
            'credit_cost_fixed': 0,
            'credit_cost_per_second': 8500,
            'max_duration': 10,
            'priority': 95,
            'is_premium': True,
            'supports_audio': True,
            'supports_image_reference': True,
            'capabilities': ['t2v', 'i2v', 'audio', 'ultra_cinema', 'native_sound', '4k_upscale'],
            'supported_aspect_ratios': ['16:9', '9:16', '1:1', '21:9'],
        },
    ]

    for m in models_data:
        obj, created = AIModel.objects.update_or_create(
            model_id=m['model_id'],
            defaults={
                'provider': provider,
                'display_name': m['display_name'],
                'modality': m['modality'],
                'credit_cost_fixed': m['credit_cost_fixed'],
                'credit_cost_per_second': m['credit_cost_per_second'],
                'max_duration': m['max_duration'],
                'priority': m['priority'],
                'is_premium': m['is_premium'],
                'supports_audio': m.get('supports_audio', False),
                'supports_image_reference': m.get('supports_image_reference', False),
                'capabilities': m['capabilities'],
                'supported_aspect_ratios': m['supported_aspect_ratios'],
                'is_enabled': True,
            }
        )
        print(f"  {'Created' if created else 'Updated'} Model: {obj.display_name} (Fixed: {obj.credit_cost_fixed}, Per-Sec: {obj.credit_cost_per_second})")

    print("\n--- Seeding Cleaverloop Subscription Plans ---")
    plans_data = [
        {
            'slug': 'free',
            'name': 'Free Trial',
            'tagline': 'Explore AI image generation with 500 bonus credits',
            'badge_text': 'TRIAL',
            'description': 'Test fast draft generation immediately with 500 starter credits upon signup.',
            'price_monthly': 0.00,
            'price_annually': 0.00,
            'credits_per_month': 500,
            'max_parallel_generations': 1,
            'max_parallel_videos': 0,
            'max_parallel_images': 1,
            'max_characters': 1,
            'max_voice_profiles': 0,
            'voice_generation_credit_cost': 25,
            'voice_clone_credit_cost': 0,
            'can_clone_voices': False,
            'video_models_access': 'Paid plans only',
            'has_all_models_access': False,
            'has_unlimited_fast_models': False,
            'features': [
                '500 Starter Credits on signup',
                '2 Nano Banana 2 Lite images (250 credits ea)',
                '1 Character DNA profile slot',
                'Standard Studio Voice Presets (25 cr/dialogue)',
                'Community feed explore access',
                'Auto-failover model routing',
            ],
            'is_active': True,
        },
        {
            'slug': 'starter',
            'name': 'Starter',
            'tagline': 'For creators making weekly AI images and short clips',
            'badge_text': '20% OFF ANNUAL',
            'description': 'Get 90,000 monthly credits to generate high-quality photoreal images and standard Veo clips.',
            'price_monthly': 19.00,
            'price_annually': 180.00, # $15/mo equivalent
            'credits_per_month': 90000,
            'max_parallel_generations': 2,
            'max_parallel_videos': 2,
            'max_parallel_images': 2,
            'max_characters': 5,
            'max_voice_profiles': 3,
            'voice_generation_credit_cost': 15,
            'voice_clone_credit_cost': 50,
            'can_clone_voices': True,
            'video_models_access': 'Veo 3.1 Lite (10k cr/clip)',
            'has_all_models_access': False,
            'has_unlimited_fast_models': False,
            'features': [
                '90,000 credits/month (Refreshes monthly)',
                '≈ 120 Nano Banana 2 Standard images',
                '≈ 360 Nano Banana 2 Lite drafts',
                '≈ 9 Veo 3.1 Lite clips (5s motion @ 10k cr)',
                'Up to 5 persistent Character DNA slots',
                '3 Custom Neural Voice Clone profiles',
                'Spoken Dialogue & TTS (15 cr/clip)',
                '2 concurrent generation slots',
                'Standard rendering queue',
                'Commercial usage rights',
            ],
            'is_active': True,
        },
        {
            'slug': 'creator',
            'name': 'Creator',
            'tagline': 'For power creators producing viral stories & campaigns',
            'badge_text': 'MOST POPULAR',
            'description': '400,000 monthly credits + Unlimited Relaxed generations so you never run out of creations.',
            'price_monthly': 59.00,
            'price_annually': 588.00, # $49/mo equivalent
            'credits_per_month': 400000,
            'max_parallel_generations': 4,
            'max_parallel_videos': 3,
            'max_parallel_images': 4,
            'max_characters': 15,
            'max_voice_profiles': 10,
            'voice_generation_credit_cost': 10,
            'voice_clone_credit_cost': 25,
            'can_clone_voices': True,
            'video_models_access': 'Veo 3.1 Fast & Lite + Unlimited Relaxed',
            'has_all_models_access': True,
            'has_unlimited_fast_models': True,
            'features': [
                '400,000 priority credits/month',
                '✨ UNLIMITED Relaxed Generations (0 credits when balance is 0)',
                '≈ 530 Nano Banana 2 Standard images',
                '≈ 1,600 Nano Banana 2 Lite drafts',
                '≈ 18 Veo 3.1 Fast videos (5s with native audio)',
                '≈ 40 Veo 3.1 Lite videos (5s)',
                '≈ 9 Veo 3.1 Cinema videos (5s)',
                'Up to 15 Character DNA slots',
                '10 Custom Neural Voice Clone slots',
                'Spoken Dialogue & TTS (10 cr / Unlimited Relaxed)',
                '4 concurrent render slots',
                'Priority queue processing',
                'Super Agent Director reasoning suite',
            ],
            'is_active': True,
        },
        {
            'slug': 'ultra',
            'name': 'Ultra / Pro',
            'tagline': 'For studios, agencies, and high-velocity directors',
            'badge_text': 'BEST VALUE',
            'description': '1,000,000 monthly credits + Unlimited Relaxed generations + 8 concurrent rendering slots.',
            'price_monthly': 129.00,
            'price_annually': 1188.00, # $99/mo equivalent
            'credits_per_month': 1000000,
            'max_parallel_generations': 8,
            'max_parallel_videos': 6,
            'max_parallel_images': 8,
            'max_characters': 0, # 0 = unlimited
            'max_voice_profiles': 0, # 0 = unlimited
            'voice_generation_credit_cost': 5,
            'voice_clone_credit_cost': 0,
            'can_clone_voices': True,
            'video_models_access': 'Full Catalog + 4K Cinema + Unlimited',
            'has_all_models_access': True,
            'has_unlimited_fast_models': True,
            'has_priority_support': True,
            'features': [
                '1,000,000 priority credits/month',
                '✨ UNLIMITED Relaxed Generations on all standard models',
                '≈ 1,330 Nano Banana 2 Standard images',
                '≈ 4,000 Nano Banana 2 Lite drafts',
                '≈ 45 Veo 3.1 Fast videos (5s with native audio)',
                '≈ 23 Veo 3.1 Cinema videos (5s)',
                'Unlimited Character DNA profiles',
                'Unlimited Neural Voice Clones (0 cr setup)',
                'VIP Ultra-fast Voice Synthesis (5 cr / Unlimited)',
                '8 concurrent generation render slots',
                'VIP Instant GPU Priority Queue',
                '24/7 dedicated support & early feature access',
            ],
            'is_active': True,
        },
    ]

    for p in plans_data:
        obj, created = SubscriptionPlan.objects.update_or_create(
            slug=p['slug'],
            defaults=p
        )
        print(f"  {'Created' if created else 'Updated'} Plan: {obj.name} (${obj.price_monthly}/mo, {obj.credits_per_month:,} cr)")

    # Ensure any existing test wallets have at least free tier
    for wallet in CreditWallet.objects.all():
        if not wallet.subscription_tier:
            wallet.subscription_tier = 'free'
            wallet.save(update_fields=['subscription_tier'])

    print("\n--- Seeding complete! ---")

if __name__ == '__main__':
    seed_all()
