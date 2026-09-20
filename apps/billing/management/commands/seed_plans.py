from django.core.management.base import BaseCommand
from apps.billing.models import SubscriptionPlan

class Command(BaseCommand):
    help = "Seed or update subscription plans for Free ($0), Starter ($15), Creator ($45), and Ultra ($75)"

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
                "price_monthly": 15.00,
                "price_annually": 144.00,
                "credits_per_month": 3000,
                "tagline": "For people exploring AI content",
                "badge_text": "",
                "can_access_premium_models": False,
                "max_parallel_generations": 2,
                "max_parallel_videos": 2,
                "max_parallel_images": 2,
                "max_characters": 5,
                "video_models_access": "Standard only",
                "has_all_models_access": False,
                "has_unlimited_fast_models": False,
                "has_early_access": False,
                "has_priority_support": False,
                "features": [
                    "Access to Character builder",
                    "Full access to Studio and Selected Apps",
                    "Up to 5 custom characters",
                    "3,000 Credits / month (~60 images or 12 videos)",
                    "Standard video models & all image models"
                ],
                "is_active": True
            },
            {
                "name": "Creator",
                "slug": "creator",
                "price_monthly": 45.00,
                "price_annually": 432.00,
                "credits_per_month": 10000,
                "tagline": "For creators making real AI videos",
                "badge_text": "MOST POPULAR",
                "can_access_premium_models": True,
                "max_parallel_generations": 4,
                "max_parallel_videos": 3,
                "max_parallel_images": 4,
                "max_characters": 15,
                "video_models_access": "All models",
                "has_all_models_access": True,
                "has_unlimited_fast_models": True,
                "has_early_access": True,
                "has_priority_support": False,
                "features": [
                    "Access to Character builder",
                    "Full access to Studio and All Apps",
                    "Up to 15 custom characters",
                    "10,000 Credits / month (~200 images or 40 videos)",
                    "Full access to all models (Veo 3.1, Kling 2.6, Seedance 2.5)",
                    "Early access to new trends & features",
                    "1080p Full HD Video rendering"
                ],
                "is_active": True
            },
            {
                "name": "Ultra",
                "slug": "ultra",
                "price_monthly": 75.00,
                "price_annually": 720.00,
                "credits_per_month": 25000,
                "tagline": "For creators building AI projects",
                "badge_text": "BEST VALUE",
                "can_access_premium_models": True,
                "max_parallel_generations": 8,
                "max_parallel_videos": 8,
                "max_parallel_images": 8,
                "max_characters": 0,  # 0 means Unlimited
                "video_models_access": "All models",
                "has_all_models_access": True,
                "has_unlimited_fast_models": True,
                "has_early_access": True,
                "has_priority_support": True,
                "features": [
                    "Access to Character builder",
                    "Full access to Studio and All Apps",
                    "Unlimited custom characters",
                    "25,000 Credits / month (~500 images or 100 videos)",
                    "Full access to all models with dedicated fast queue",
                    "Early access to advanced AI features",
                    "4K Rendering & FFmpeg Multi-Scene Assembly",
                    "24/7 Priority Support"
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
