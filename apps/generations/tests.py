from django.test import TestCase
from apps.accounts.models import User
from apps.credits.models import CreditWallet
from apps.credits.services import CreditService
from apps.generations.models import Generation
from apps.generations.tasks import dispatch_generation_task
from apps.providers.models import AIProviderConfig, AIModel
from apps.providers.registry import ModelRegistry

class GenerationWorkflowTests(TestCase):
    def setUp(self):
        ModelRegistry.seed_initial_catalog()
        self.user = User.objects.create_user(email="creator@cleaverloop.ai", username="creator", password="password123")
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

    def test_failed_generation_refunds_credits(self):
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

    def test_automatic_runtime_failover_when_primary_provider_fails(self):
        """Verify dynamic failover when primary provider fails submission."""
        google_model = AIModel.objects.filter(model_id="veo-3.1-fast-generate-preview").first()
        self.assertIsNotNone(google_model)

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

        # Dispatch generation: Google fails, triggering automatic failover
        dispatch_generation_task(str(gen.id))

        gen.refresh_from_db()
        # Verify that generation failed over to alternative model
        self.assertNotEqual(gen.model.id, google_model.id)
        self.assertIn(gen.status, ("completed", "queued", "processing"))
        if gen.status == "completed":
            self.assertIsNotNone(gen.output_media)
            self.assertTrue("failover" in gen.admin_error_detail.lower() or "fallback" in gen.admin_error_detail.lower())


    def test_character_idor_prevented(self):
        """Verify passing another user's character_id sets character to None."""
        from django.test import Client
        from apps.characters.models import Character
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
        from django.test import Client
        from django.core.files.uploadedfile import SimpleUploadedFile
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
