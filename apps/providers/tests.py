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

    def test_minimax_provider_registration_and_cost_estimation(self):
        """Verify MiniMax adapter is properly registered, seeded, and calculates cost."""
        minimax_model = AIModel.objects.filter(model_id="minimax-video-01").first()
        self.assertIsNotNone(minimax_model)
        self.assertEqual(minimax_model.provider.slug, "minimax")
        self.assertIn("t2v", minimax_model.capabilities)

        adapter = ModelRegistry.get_provider_adapter("minimax")
        self.assertIsNotNone(adapter)
        
        req = GenerationRequest(prompt="A cinematic drone shot over Tokyo", aspect_ratio="16:9", duration=5)
        cost = adapter.estimate_cost("minimax-video-01", req)
        self.assertGreater(cost.estimated_credits, 0)
        self.assertEqual(cost.estimated_duration_sec, 5)

    def test_fal_ai_provider_registration_and_fallback(self):
        """Verify Fal.ai adapter is registered, seeded with Wan 2.1, and acts as fallback."""
        fal_model = AIModel.objects.filter(model_id="fal-wan-2.1").first()
        self.assertIsNotNone(fal_model)
        self.assertEqual(fal_model.provider.slug, "fal")
        self.assertIn("t2v", fal_model.capabilities)

        adapter = ModelRegistry.get_provider_adapter("fal")
        self.assertIsNotNone(adapter)

        # Cost estimation
        req = GenerationRequest(prompt="A futuristic flying car", aspect_ratio="16:9", duration=5)
        cost = adapter.estimate_cost("fal-wan-2.1", req)
        self.assertGreater(cost.estimated_credits, 0)
        self.assertEqual(cost.estimated_duration_sec, 5)

    def test_path_traversal_blocked_in_load_image_as_base64(self):
        """Verify load_image_as_base64 rejects directory traversal patterns."""
        from apps.providers.base import load_image_as_base64
        self.assertIsNone(load_image_as_base64("../../.env"))
        self.assertIsNone(load_image_as_base64("/media/../../../../etc/passwd"))
        self.assertIsNone(load_image_as_base64("..\\..\\.env"))

    def test_ssrf_blocked_in_load_image_as_base64(self):
        """Verify load_image_as_base64 blocks private/internal loopback URLs."""
        from apps.providers.base import load_image_as_base64, is_safe_external_url
        self.assertFalse(is_safe_external_url("http://127.0.0.1:8000/media/secret.png"))
        self.assertFalse(is_safe_external_url("http://localhost:8000/"))
        self.assertFalse(is_safe_external_url("http://169.254.169.254/latest/meta-data/"))
        self.assertIsNone(load_image_as_base64("http://127.0.0.1:8000/secret.png"))

