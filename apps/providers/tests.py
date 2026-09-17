from django.test import TestCase
from apps.providers.models import AIProviderConfig, AIModel
from apps.providers.router import ModelRouter, NoEligibleModelError
from apps.providers.registry import ModelRegistry
from apps.providers.base import GenerationRequest

class ProviderRegistryAndRouterTests(TestCase):
    def setUp(self):
        ModelRegistry.seed_initial_catalog()

    def test_mock_provider_synthetic_generation(self):
        """Verify MockAIProvider generates valid image and video assets."""
        adapter = ModelRegistry.get_provider_adapter("mock")
        self.assertIsNotNone(adapter)

        # Image generation test
        img_req = GenerationRequest(prompt="A futuristic neon city", aspect_ratio="16:9")
        img_res = adapter.generate_image("cleverloop-mock-image", img_req)
        self.assertEqual(img_res.status, "completed")
        self.assertTrue(img_res.output_media_url.endswith(".png"))

        # Video generation test
        vid_req = GenerationRequest(prompt="A spaceship flying through an asteroid field", aspect_ratio="16:9", duration=5)
        vid_res = adapter.generate_video("cleverloop-mock-video", vid_req)
        self.assertEqual(vid_res.status, "completed")
        self.assertTrue(vid_res.output_media_url.endswith(".webp"))

    def test_model_router_capability_matching(self):
        """Verify ModelRouter filters models based on requested duration and modality."""
        # Video with 5s duration
        video_model = ModelRouter.select_model(modality="video", user_preference="automatic", duration=5)
        self.assertEqual(video_model.modality, "video")
        self.assertGreaterEqual(video_model.max_duration, 5)

        # Image model
        image_model = ModelRouter.select_model(modality="image", user_preference="automatic")
        self.assertEqual(image_model.modality, "image")

    def test_model_router_fallback_when_provider_offline(self):
        """Verify router falls back gracefully when preferred provider is marked offline."""
        mock_provider = AIProviderConfig.objects.get(slug="mock")
        mock_provider.health_status = "offline"
        mock_provider.save()

        # Should route to next enabled provider with video capabilities
        selected = ModelRouter.select_model(modality="video", user_preference="automatic", duration=5)
        self.assertNotEqual(selected.provider.slug, "mock")
        self.assertEqual(selected.modality, "video")
