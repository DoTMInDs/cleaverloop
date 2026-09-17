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
        self.user = User.objects.create_user(email="creator@cleverloop.ai", username="creator", password="password123")
        self.model = AIModel.objects.get(model_id="cleverloop-mock-video")
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
