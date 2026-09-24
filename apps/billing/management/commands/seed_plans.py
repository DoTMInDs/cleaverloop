from django.core.management.base import BaseCommand
from apps.billing.models import SubscriptionPlan

class Command(BaseCommand):
    help = "Seed or update subscription plans for Free ($0), Starter ($19), Creator ($59), and Ultra ($129) with Flashloop economics"

    def handle(self, *args, **options):
        plans_data = [
            {
                "name": "Free Starter",
                "slug": "free-starter",
                "price_monthly": 0.00,
                "price_annually": 0.00,
                "credits_per_month": 500,
                "tagline": "For exploring AI media creation",
                "badge_text": "",
                "can_access_premium_models": False,
                "max_parallel_generations": 1,
                "max_parallel_videos": 1,
                "max_parallel_images": 1,
                "max_characters": 1,
                "video_models_access": "Standard only",
                "has_all_models_access": False,
                "has_unlimited_fast_models": False,
                "has_early_access": False,
                "has_priority_support": False,
                "features": [
                    "500 Starter Credits",
                    "Access to Standard Models",
                    "720p Video Generation",
                    "Community Support"
                ],
                "is_active": True
            },
            {
                "name": "Starter",
                "slug": "starter",
                "price_monthly": 19.00,
                "price_annually": 180.00,
                "credits_per_month": 90000,
                "tagline": "For creators making weekly AI images and short clips",
                "badge_text": "20% OFF ANNUAL",
                "can_access_premium_models": False,
                "max_parallel_generations": 2,
                "max_parallel_videos": 2,
                "max_parallel_images": 2,
                "max_characters": 5,
                "max_voice_profiles": 3,
                "voice_generation_credit_cost": 15,
                "voice_clone_credit_cost": 50,
                "can_clone_voices": True,
                "video_models_access": "Veo 3.1 Lite (10k cr/clip)",
                "has_all_models_access": False,
                "has_unlimited_fast_models": False,
                "has_early_access": False,
                "has_priority_support": False,
                "features": [
                    "90,000 credits/month (Refreshes monthly)",
                    "≈ 120 Nano Banana 2 Standard images",
                    "≈ 360 Nano Banana 2 Lite drafts",
                    "≈ 9 Veo 3.1 Lite clips (5s motion @ 10k cr)",
                    "Up to 5 persistent Character DNA slots",
                    "3 Custom Neural Voice Clone profiles",
                    "Spoken Dialogue & TTS (15 cr/clip)",
                    "2 concurrent generation slots",
                    "Standard rendering queue",
                    "Commercial usage rights"
                ],
                "is_active": True
            },
            {
                "name": "Creator",
                "slug": "creator",
                "price_monthly": 59.00,
                "price_annually": 588.00,
                "credits_per_month": 400000,
                "tagline": "For power creators producing viral stories & campaigns",
                "badge_text": "MOST POPULAR",
                "can_access_premium_models": True,
                "max_parallel_generations": 4,
                "max_parallel_videos": 3,
                "max_parallel_images": 4,
                "max_characters": 15,
                "max_voice_profiles": 10,
                "voice_generation_credit_cost": 10,
                "voice_clone_credit_cost": 25,
                "can_clone_voices": True,
                "video_models_access": "Veo 3.1 Fast & Lite + Unlimited Relaxed",
                "has_all_models_access": True,
                "has_unlimited_fast_models": True,
                "has_early_access": True,
                "has_priority_support": False,
                "features": [
                    "400,000 priority credits/month",
                    "✨ UNLIMITED Relaxed Generations (0 credits when balance is 0)",
                    "≈ 530 Nano Banana 2 Standard images",
                    "≈ 1,600 Nano Banana 2 Lite drafts",
                    "≈ 18 Veo 3.1 Fast videos (5s with native audio)",
                    "≈ 40 Veo 3.1 Lite videos (5s)",
                    "≈ 9 Veo 3.1 Cinema videos (5s)",
                    "Up to 15 Character DNA slots",
                    "10 Custom Neural Voice Clone slots",
                    "Spoken Dialogue & TTS (10 cr / Unlimited Relaxed)",
                    "4 concurrent render slots",
                    "Priority queue processing",
                    "Super Agent Director reasoning suite"
                ],
                "is_active": True
            },
            {
                "name": "Ultra / Pro",
                "slug": "ultra",
                "price_monthly": 129.00,
                "price_annually": 1188.00,
                "credits_per_month": 1000000,
                "tagline": "For studios, agencies, and high-velocity directors",
                "badge_text": "BEST VALUE",
                "can_access_premium_models": True,
                "max_parallel_generations": 8,
                "max_parallel_videos": 6,
                "max_parallel_images": 8,
                "max_characters": 0,  # 0 means Unlimited
                "max_voice_profiles": 0,  # 0 means Unlimited
                "voice_generation_credit_cost": 5,
                "voice_clone_credit_cost": 0,
                "can_clone_voices": True,
                "video_models_access": "Full Catalog (Cinema Master, Fast, Lite) + 4K Cinema + Unlimited",
                "has_all_models_access": True,
                "has_unlimited_fast_models": True,
                "has_early_access": True,
                "has_priority_support": True,
                "features": [
                    "1,000,000 priority credits/month",
                    "✨ UNLIMITED Relaxed Generations on all standard models",
                    "≈ 1,330 Nano Banana 2 Standard images",
                    "≈ 4,000 Nano Banana 2 Lite drafts",
                    "≈ 45 Veo 3.1 Fast videos (5s with native audio)",
                    "≈ 23 Veo 3.1 Cinema videos (5s)",
                    "Unlimited Character DNA profiles",
                    "Unlimited Neural Voice Clones (0 cr setup)",
                    "VIP Ultra-fast Voice Synthesis (5 cr / Unlimited)",
                    "8 concurrent generation render slots",
                    "VIP Instant GPU Priority Queue",
                    "24/7 dedicated support & early feature access"
                ],
                "is_active": True
            }
        ]

        # Deactivate any legacy plans that are not in this list
        valid_slugs = [p["slug"] for p in plans_data]
        SubscriptionPlan.objects.exclude(slug__in=valid_slugs).update(is_active=False)

        for p_data in plans_data:
            slug = p_data.pop("slug")
            plan, created = SubscriptionPlan.objects.update_or_create(
                slug=slug,
                defaults=p_data
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} plan '{plan.name}' (${plan.price_monthly}/mo, {plan.credits_per_month} credits)"))
