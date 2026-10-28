from unittest.mock import patch
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User
from apps.characters.models import Character
from apps.credits.models import CreditWallet
from apps.credits.services import CreditService
from apps.generations.models import Generation
from apps.generations.tasks import dispatch_generation_task
from apps.providers.base import ProviderJobResult
from apps.providers.models import AIProviderConfig, AIModel
from apps.providers.registry import ModelRegistry
from apps.providers.router import ModelRouter


class GenerationWorkflowTests(TestCase):
    def setUp(self):
        ModelRegistry.seed_initial_catalog()
        self.user = User.objects.create_user(email="creator@cleaverloop.ai", username="creator", password="password123")
        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'starter'
        wallet.balance = 90000
        wallet.save()
        self.model = AIModel.objects.get(model_id="cleaverloop-mock-video")
        self.provider = self.model.provider

    def test_successful_generation_workflow(self):
        """End-to-end test of generation dispatch, media creation, and credit settlement."""
        wallet = CreditWallet.objects.get(user=self.user)
        initial_balance = wallet.balance

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.model,
            model_id_snapshot=self.model.model_id,
            prompt="A majestic eagle soaring over snow-capped mountains",
            duration=5,
            status="queued"
        )

        cost = self.model.calculate_credit_cost(duration=5)
        CreditService.reserve_credits(self.user, cost, gen)

        # Run task synchronously for test
        dispatch_generation_task(str(gen.id))

        gen.refresh_from_db()
        wallet.refresh_from_db()

        self.assertEqual(gen.status, "completed")
        self.assertIsNotNone(gen.output_media)
        self.assertEqual(wallet.balance, initial_balance - cost)
        self.assertEqual(gen.credits_consumed, cost)

    @patch('apps.providers.router.ModelRouter.get_fallback_model', return_value=None)
    def test_failed_generation_refunds_credits(self, mock_fallback):
        """Verify simulated failure immediately restores user credits."""
        wallet = CreditWallet.objects.get(user=self.user)
        initial_balance = wallet.balance

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.model,
            model_id_snapshot=self.model.model_id,
            prompt="Trigger fail for test",
            duration=5,
            status="queued"
        )

        cost = self.model.calculate_credit_cost(duration=5)
        CreditService.reserve_credits(self.user, cost, gen)

        # Run task synchronously
        dispatch_generation_task(str(gen.id))

        gen.refresh_from_db()
        wallet.refresh_from_db()

        self.assertEqual(gen.status, "failed")
        self.assertEqual(wallet.balance, initial_balance)  # Fully refunded!
        self.assertIn("restored to your wallet", gen.error_message)

    @patch('apps.providers.router.ModelRouter.get_fallback_model')
    @patch('apps.providers.adapters.google_veo.GoogleVeoProvider.generate_video')
    def test_automatic_runtime_failover_when_primary_provider_fails(self, mock_veo, mock_get_fallback):
        """Verify dynamic failover when primary provider fails submission."""
        mock_veo.return_value = ProviderJobResult(
            external_job_id="",
            status="failed",
            error_message="Google Veo API error (429): Quota exceeded"
        )
        google_model = AIModel.objects.filter(model_id="veo-3.1-fast-generate-preview").first()
        self.assertIsNotNone(google_model)

        mock_fallback = AIModel.objects.get(model_id="cleaverloop-mock-video")
        mock_get_fallback.return_value = mock_fallback

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=google_model.provider,
            model=google_model,
            model_id_snapshot=google_model.model_id,
            prompt="A sleek hovercar flying over a cyberpunk metropolis",
            duration=5,
            status="queued"
        )
        cost = google_model.calculate_credit_cost(duration=5)
        CreditService.reserve_credits(self.user, cost, gen)

        # Dispatch generation: Google fails, triggering automatic failover to mock_fallback
        dispatch_generation_task(str(gen.id))

        gen.refresh_from_db()
        # Verify that generation failed over to alternative model
        self.assertNotEqual(gen.model.id, google_model.id)
        self.assertEqual(gen.model.id, mock_fallback.id)
        self.assertEqual(gen.status, "completed")
        self.assertIsNotNone(gen.output_media)
        self.assertTrue("failover" in gen.admin_error_detail.lower() or "fallback" in gen.admin_error_detail.lower())

    @patch('apps.generations.tasks.dispatch_generation_task.delay')
    def test_character_idor_prevented(self, mock_dispatch):
        """Verify passing another user's character_id sets character to None."""
        other_user = User.objects.create_user(email="other@cleaverloop.ai", username="otheruser", password="password123")
        other_char = Character.objects.create(
            owner=other_user,
            name="Secret Avatar",
            appearance_description="A mysterious hooded rogue"
        )

        client = Client()
        client.force_login(self.user)
        resp = client.post('/generations/create/', {
            'generation_type': 'video',
            'prompt': 'A hero standing on a cliff',
            'duration': 5,
            'aspect_ratio': '16:9',
            'character_id': str(other_char.id),
        })
        self.assertEqual(resp.status_code, 200)

        gen = Generation.objects.filter(user=self.user).order_by('-created_at').first()
        self.assertIsNone(gen.character)

    def test_invalid_file_extension_rejected(self):
        """Verify uploaded reference file with forbidden extension is rejected."""
        client = Client()
        client.force_login(self.user)

        bad_file = SimpleUploadedFile("malicious.exe", b"MZ_MALICIOUS_BYTES", content_type="application/x-msdownload")
        resp = client.post('/generations/create/', {
            'generation_type': 'video',
            'prompt': 'A hero standing on a cliff',
            'duration': 5,
            'aspect_ratio': '16:9',
            'reference_file': bad_file
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported file type", resp.content.decode('utf-8'))

    @patch('apps.generations.tasks.dispatch_generation_task.delay')
    def test_batch_generation_and_modality_concurrency_limits(self, mock_dispatch):
        """Verify batch_count creates multiple generations up to tier modality concurrency limits."""
        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'creator'  # allows 3 parallel videos, 4 parallel images
        wallet.balance = 500000
        wallet.save()

        client = Client()
        client.force_login(self.user)

        # Request batch of 3 images -> should create 3 queued generations
        resp = client.post('/generations/create/', {
            'generation_type': 'image',
            'prompt': 'Cyberpunk skyline at dusk',
            'aspect_ratio': '16:9',
            'batch_count': 3,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Generation.objects.filter(user=self.user, generation_type='image', status='queued').count(), 3)

        # Now 3 image jobs are active; requesting a batch of 2 more exceeds Creator max_parallel_images (4)
        resp_exceed = client.post('/generations/create/', {
            'generation_type': 'image',
            'prompt': 'Another batch',
            'batch_count': 2,
        })
        self.assertEqual(resp_exceed.status_code, 429)
        self.assertIn("Image concurrency limit reached", resp_exceed.content.decode('utf-8'))

    @patch('apps.generations.tasks.dispatch_generation_task.delay')
    def test_upscale_edit_and_voice_translate_modes(self, mock_dispatch):
        """Verify upscale (2x/4x), edit by typing, and voice studio modes create valid generations."""
        client = Client()
        client.force_login(self.user)

        # 1. Upscale 4x
        resp_up = client.post('/generations/create/', {
            'generation_type': 'upscale',
            'upscale_scale': '4x',
            'prompt': 'Crisp architectural photography',
        })
        self.assertEqual(resp_up.status_code, 200)
        up_gen = Generation.objects.filter(user=self.user, generation_type='upscale').first()
        self.assertIsNotNone(up_gen)
        self.assertIn('[Upscale 4x]', up_gen.prompt)

        # 2. Edit by typing
        Generation.objects.filter(user=self.user).update(status='completed')
        resp_edit = client.post('/generations/create/', {
            'generation_type': 'edit',
            'prompt': 'Replace sky with aurora borealis',
        })
        self.assertEqual(resp_edit.status_code, 200)
        self.assertTrue(Generation.objects.filter(user=self.user, generation_type='edit').exists())

        # 3. Voice Studio with emotion tag and translation
        Generation.objects.filter(user=self.user).update(status='completed')
        resp_voice = client.post('/generations/create/', {
            'generation_type': 'voice',
            'voice_mode': 'translate',
            'target_language': 'Spanish',
            'prompt': '[excited] Welcome to the future of cinema!',
        })
        self.assertEqual(resp_voice.status_code, 200)
        audio_gen = Generation.objects.filter(user=self.user, generation_type='audio').first()
        self.assertIsNotNone(audio_gen)
        self.assertIn('[Translate to Spanish]', audio_gen.prompt)
        self.assertIn('[excited]', audio_gen.prompt)

    def test_recreate_deep_link_in_create_studio(self):
        """Verify ?recreate=<id> populates Create Studio context with source generation parameters."""
        gen = Generation.objects.create(
            user=self.user,
            generation_type='video',
            provider=self.provider,
            model=self.model,
            model_id_snapshot=self.model.model_id,
            prompt='A dramatic noir detective in a rain-drenched alley',
            aspect_ratio='21:9',
            duration=10,
            status='completed'
        )
        client = Client()
        client.force_login(self.user)
        resp = client.get(f'/studio/create/?recreate={gen.id}&tab=upscale')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['recreate_generation'].id, gen.id)
        html = resp.content.decode('utf-8')
        self.assertIn('A dramatic noir detective in a rain-drenched alley', html)
        self.assertIn('Super-Resolution Neural Upscaler', html)
        self.assertIn('Batch Variations', html)

    def test_explore_page_viral_effects_and_persistent_community_likes(self):
        """Verify Explore 2.0 renders Viral Effects shelf and persists community likes."""
        gen = Generation.objects.create(
            user=self.user,
            generation_type='video',
            provider=self.provider,
            model=self.model,
            model_id_snapshot=self.model.model_id,
            prompt='A sleek cyber sports car racing through neon tunnels',
            status='completed'
        )
        client = Client()
        client.force_login(self.user)

        # Toggle community like ON
        like_resp = client.post(f'/generations/{gen.id}/like/')
        self.assertEqual(like_resp.status_code, 200)
        data = like_resp.json()
        self.assertTrue(data['liked'])
        first_count = data['likes_count']

        # Toggle community like OFF
        unlike_resp = client.post(f'/generations/{gen.id}/like/')
        self.assertEqual(unlike_resp.status_code, 200)
        self.assertFalse(unlike_resp.json()['liked'])
        self.assertEqual(unlike_resp.json()['likes_count'], first_count - 1)

        # Explore view renders hero bar & viral effects
        exp_resp = client.get('/studio/explore/')
        self.assertEqual(exp_resp.status_code, 200)
        self.assertGreaterEqual(len(exp_resp.context['viral_effects']), 6)
        self.assertIn('Explore What Creators Are Shipping', exp_resp.content.decode('utf-8'))

    @patch('apps.generations.tasks.dispatch_generation_task.delay')
    def test_pro_style_preset_camera_motion_sfx_and_prompt_enhancer(self, mock_dispatch):
        """Verify style_preset, camera_motion, auto_sfx, source_image_url, and prompt enhancer API."""
        client = Client()
        client.force_login(self.user)

        # 1. Enhance Prompt API
        enh_resp = client.post('/generations/api/enhance-prompt/', {
            'prompt': 'A lone astronaut walking on Mars',
            'modality': 'video',
            'style_preset': 'film_35mm',
            'camera_motion': 'Slow Dolly In',
        })
        self.assertEqual(enh_resp.status_code, 200)
        enhanced = enh_resp.json()['enhanced_prompt']
        self.assertIn('Slow Dolly In', enhanced)

        # 2. Create video with style_preset, camera_motion, auto_sfx, and source_image_url
        gen_resp = client.post('/generations/create/', {
            'generation_type': 'video',
            'prompt': 'A lone astronaut walking on Mars',
            'style_preset': 'film_35mm',
            'camera_motion': '360 Orbit',
            'auto_sfx': 'true',
            'sfx_prompt': 'deep Martian wind and suit breathing',
            'source_image_url': '/static/images/showcase/brand_video_car.jpg',
            'duration': 5,
        })
        self.assertEqual(gen_resp.status_code, 200)
        gen = Generation.objects.filter(user=self.user).order_by('-created_at').first()
        self.assertIn('Kodak Vision3 500T 35mm', gen.prompt)
        self.assertIn('[Camera Motion: 360 Orbit]', gen.prompt)
        self.assertIn('[SFX: deep Martian wind and suit breathing]', gen.prompt)
        self.assertTrue(gen.reference_media.exists())


