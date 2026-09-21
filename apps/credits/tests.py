from django.test import TestCase, TransactionTestCase
from apps.accounts.models import User
from apps.credits.models import CreditWallet, CreditTransaction
from apps.credits.services import CreditService, InsufficientCreditsError
from apps.generations.models import Generation
from apps.providers.models import AIProviderConfig, AIModel

class CreditLedgerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="test@cleaverloop.ai", username="testuser", password="password123")
        self.provider = AIProviderConfig.objects.create(slug="mock", name="Mock Provider")
        self.image_model = AIModel.objects.create(
            provider=self.provider,
            model_id="nano-banana-2-lite",
            display_name="Nano Banana 2 Lite",
            modality="image",
            credit_cost_fixed=250,
            credit_cost_per_second=0
        )
        self.video_model = AIModel.objects.create(
            provider=self.provider,
            model_id="veo-3.1-fast",
            display_name="Veo 3.1 Fast",
            modality="video",
            credit_cost_fixed=0,
            credit_cost_per_second=4400
        )

    def test_starter_credits_granted_on_user_creation(self):
        """Verify new users automatically receive 500 starter credits on signup."""
        wallet = CreditWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 500)
        self.assertEqual(wallet.subscription_tier, 'free')
        self.assertEqual(wallet.lifetime_earned, 500)
        self.assertEqual(wallet.transactions.count(), 1)
        self.assertEqual(wallet.transactions.first().transaction_type, 'bonus')

    def test_free_tier_can_generate_draft_image(self):
        """Verify free tier users can generate Nano Banana 2 Lite images (250 credits each)."""
        wallet = CreditWallet.objects.get(user=self.user)
        initial_balance = wallet.balance

        gen = Generation.objects.create(
            user=self.user,
            generation_type="image",
            provider=self.provider,
            model=self.image_model,
            model_id_snapshot=self.image_model.model_id,
            prompt="Cyberpunk neon city street",
            duration=0
        )

        cost = self.image_model.calculate_credit_cost()
        self.assertEqual(cost, 250)

        CreditService.reserve_credits(self.user, cost, gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance - 250)

        CreditService.commit_credits(gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 250)

    def test_free_tier_video_gating(self):
        """Verify free tier users are blocked from generating videos to prevent bot abuse."""
        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.video_model,
            model_id_snapshot=self.video_model.model_id,
            prompt="Cinematic drone sweep over mountains",
            duration=5
        )

        cost = self.video_model.calculate_credit_cost(duration=5)
        with self.assertRaises(InsufficientCreditsError) as ctx:
            CreditService.reserve_credits(self.user, cost, gen)
        self.assertIn("paid subscription", str(ctx.exception).lower())

    def test_paid_tier_video_reservation_and_commit(self):
        """Verify paid subscriber can reserve and commit video generation credits."""
        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'starter'
        wallet.balance = 90000
        wallet.save()

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.video_model,
            model_id_snapshot=self.video_model.model_id,
            prompt="Cinematic drone sweep over mountains",
            duration=5
        )

        cost = self.video_model.calculate_credit_cost(duration=5)  # 5 * 4400 = 22,000
        self.assertEqual(cost, 22000)

        CreditService.reserve_credits(self.user, cost, gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 90000 - 22000)
        self.assertEqual(gen.credits_reserved, 22000)

        CreditService.commit_credits(gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 68000)
        self.assertEqual(wallet.lifetime_spent, 22000)

    def test_unlimited_relaxed_generation_for_creator_tier(self):
        """Verify Creator/Ultra users can generate in relaxed queue for 0 credits when balance is 0."""
        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'creator'
        wallet.balance = 0
        wallet.save()

        self.assertTrue(wallet.is_unlimited_eligible)
        self.assertTrue(wallet.in_relaxed_mode)

        can_gen, effective_cost, msg = CreditService.can_generate(self.user, 22000, modality='video')
        self.assertTrue(can_gen)
        self.assertEqual(effective_cost, 0)
        self.assertIn("Unlimited Relaxed Queue", msg)

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.video_model,
            model_id_snapshot=self.video_model.model_id,
            prompt="Cinematic anime scene",
            duration=5
        )

        tx = CreditService.reserve_credits(self.user, 22000, gen)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, 0)
        self.assertEqual(gen.credits_reserved, 0)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 0)

    def test_refund_on_failure_restores_balance(self):
        """Verify reserved credits are fully refunded on job failure."""
        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'starter'
        wallet.balance = 50000
        wallet.save()

        gen = Generation.objects.create(
            user=self.user,
            generation_type="image",
            provider=self.provider,
            model=self.image_model,
            model_id_snapshot=self.image_model.model_id,
            prompt="Test prompt",
            duration=0
        )

        CreditService.reserve_credits(self.user, 250, gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 49750)

        # Refund
        CreditService.refund_credits(gen, reason="Provider timeout")
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 50000)
        self.assertEqual(gen.credits_reserved, 0)

    def test_double_refund_prevented_idempotency(self):
        """Verify calling refund_credits multiple times on the same generation only refunds once."""
        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'starter'
        wallet.balance = 50000
        wallet.save()

        gen = Generation.objects.create(
            user=self.user,
            generation_type="image",
            provider=self.provider,
            model=self.image_model,
            model_id_snapshot=self.image_model.model_id,
            prompt="Test prompt",
            duration=0
        )

        CreditService.reserve_credits(self.user, 250, gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 49750)

        # First refund
        tx1 = CreditService.refund_credits(gen, reason="Failure 1")
        self.assertIsNotNone(tx1)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 50000)

        # Duplicate refund call must return None and not double-credit wallet
        tx2 = CreditService.refund_credits(gen, reason="Failure 2 (Duplicate)")
        self.assertIsNone(tx2)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 50000)

    def test_max_parallel_generations_tier_mapping(self):
        """Verify concurrency limits per subscription tier."""
        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'free'
        self.assertEqual(wallet.max_parallel_generations, 1)

        wallet.subscription_tier = 'starter'
        self.assertEqual(wallet.max_parallel_generations, 2)

        wallet.subscription_tier = 'creator'
        self.assertEqual(wallet.max_parallel_generations, 4)

        wallet.subscription_tier = 'ultra'
        self.assertEqual(wallet.max_parallel_generations, 8)

    def test_reap_stale_generations_task(self):
        """Verify stale generations older than timeout are reaped and credits refunded."""
        from apps.generations.tasks import reap_stale_generations_task
        from django.utils import timezone

        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'starter'
        wallet.balance = 50000
        wallet.save()

        stale_gen = Generation.objects.create(
            user=self.user,
            generation_type="image",
            provider=self.provider,
            model=self.image_model,
            model_id_snapshot=self.image_model.model_id,
            prompt="Stale test prompt",
            duration=0,
            status='processing'
        )
        CreditService.reserve_credits(self.user, 250, stale_gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 49750)

        # Artificially age the generation created_at timestamp
        Generation.objects.filter(id=stale_gen.id).update(
            created_at=timezone.now() - timezone.timedelta(minutes=30)
        )

        reaped = reap_stale_generations_task(timeout_minutes=15)
        self.assertEqual(reaped, 1)

        stale_gen.refresh_from_db()
        self.assertEqual(stale_gen.status, 'failed')
        self.assertIn("timed out", stale_gen.admin_error_detail.lower())

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 50000)

