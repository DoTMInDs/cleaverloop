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

    def test_tier_veo_model_wiring_and_access(self):
        """Verify tier-based Veo model wiring (Starter -> Lite, Creator -> Fast, Ultra -> Standard)."""
        from apps.providers.router import ModelRouter

        # Create Veo Lite and Standard models for routing test
        veo_lite, _ = AIModel.objects.get_or_create(
            provider=self.provider,
            model_id="veo-3.1-lite",
            defaults={
                'display_name': "Veo 3.1 Lite",
                'modality': "video",
                'credit_cost_fixed': 0,
                'credit_cost_per_second': 2000,
                'max_duration': 10,
                'is_premium': False,
                'priority': 85
            }
        )
        veo_std, _ = AIModel.objects.get_or_create(
            provider=self.provider,
            model_id="veo-3.1-standard",
            defaults={
                'display_name': "Veo 3.1 Standard",
                'modality': "video",
                'credit_cost_fixed': 0,
                'credit_cost_per_second': 8500,
                'max_duration': 10,
                'is_premium': True,
                'priority': 95
            }
        )

        wallet = CreditWallet.objects.get(user=self.user)

        # Starter tier checks
        wallet.subscription_tier = 'starter'
        wallet.balance = 90000
        wallet.save()

        self.assertEqual(wallet.default_video_model, 'veo-3.1-lite')
        self.assertTrue(wallet.can_access_model('veo-3.1-lite'))
        self.assertFalse(wallet.can_access_model('veo-3.1-fast'))
        self.assertFalse(wallet.can_access_model('veo-3.1-standard'))
        self.assertFalse(wallet.can_access_premium_models)

        # Automatic routing for Starter user selects Veo Lite
        selected = ModelRouter.select_model(
            modality='video',
            user_preference='automatic',
            duration=5,
            user=self.user,
            subscription_tier='starter'
        )
        self.assertEqual(selected.model_id, 'veo-3.1-lite')
        cost_5s = selected.calculate_credit_cost(duration=5)
        self.assertEqual(cost_5s, 10000)
        self.assertEqual(90000 // cost_5s, 9)  # 9 full clips yield!

        # Creator tier checks
        wallet.subscription_tier = 'creator'
        wallet.balance = 400000
        wallet.save()

        self.assertEqual(wallet.default_video_model, 'veo-3.1-fast')
        self.assertTrue(wallet.can_access_model('veo-3.1-lite'))
        self.assertTrue(wallet.can_access_model('veo-3.1-fast'))
        self.assertTrue(wallet.can_access_model('veo-3.1-standard'))
        self.assertTrue(wallet.can_access_premium_models)

        selected_creator = ModelRouter.select_model(
            modality='video',
            user_preference='automatic',
            duration=5,
            user=self.user,
            subscription_tier='creator'
        )
        self.assertEqual(selected_creator.model_id, 'veo-3.1-fast')
        creator_cost_5s = selected_creator.calculate_credit_cost(duration=5)
        self.assertEqual(creator_cost_5s, 22000)

        # Ultra tier checks
        wallet.subscription_tier = 'ultra'
        wallet.balance = 1000000
        wallet.save()

        self.assertEqual(wallet.default_video_model, 'veo-3.1-standard')
        self.assertTrue(wallet.can_access_model('veo-3.1-standard'))
        selected_ultra = ModelRouter.select_model(
            modality='video',
            user_preference='best_quality',
            duration=5,
            user=self.user,
            subscription_tier='ultra'
        )
        self.assertEqual(selected_ultra.model_id, 'veo-3.1-standard')

    def test_purchased_credits_increment_and_legacy_type_normalization(self):
        """Verify top-up purchases increment wallet.purchased_credits and normalize 'topup' -> 'purchase'."""
        tx = CreditService.grant_credits(
            user=self.user,
            amount=25000,
            transaction_type='topup',
            description='Credit Pack Purchase',
            external_reference='pack_ref_001'
        )
        wallet = CreditWallet.objects.get(user=self.user)
        self.assertEqual(wallet.purchased_credits, 25000)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.transaction_type, 'purchase')

    def test_annual_subscription_activation_and_effective_pricing(self):
        """Verify annual billing sets 365-day period and computes discounted annual USD price."""
        from apps.billing.models import SubscriptionPlan, Subscription
        from apps.billing.paystack import PaystackService
        from decimal import Decimal

        plan = SubscriptionPlan.objects.create(
            name='Creator',
            slug='creator',
            price_monthly=Decimal('59.00'),
            price_annually=Decimal('0.00'),
            credits_per_month=400000,
        )
        effective_annual = PaystackService.get_effective_usd_price(plan, 'annual')
        self.assertEqual(effective_annual, Decimal('588.00'))
        effective_monthly = PaystackService.get_effective_usd_price(plan, 'monthly')
        self.assertEqual(effective_monthly, Decimal('59.00'))

        CreditService.activate_subscription(
            user=self.user,
            plan=plan,
            reference='sub_annual_test_01',
            billing_cycle='annual'
        )
        sub = Subscription.objects.get(user=self.user)
        delta_days = (sub.current_period_end - sub.current_period_start).days
        self.assertGreaterEqual(delta_days, 364)

    def test_tier_character_and_modality_quotas_enforced(self):
        """Verify per-tier max_characters, max_parallel_videos, and max_parallel_images."""
        from django.urls import reverse
        from apps.characters.models import Character

        wallet = CreditWallet.objects.get(user=self.user)
        wallet.subscription_tier = 'free'
        wallet.save()
        self.assertEqual(wallet.max_characters, 1)
        self.assertEqual(wallet.max_parallel_videos, 1)
        self.assertEqual(wallet.max_parallel_images, 1)

        # Create 1 character (allowed on Free)
        Character.objects.create(owner=self.user, name='Hero One')

        # Second character should be blocked by quota
        self.client.login(email='test@cleaverloop.ai', password='password123')
        resp = self.client.post(reverse('characters:generate_ai'), {'brief': 'A second hero'})
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Character limit reached', resp.json()['error'])

        # Upgrade to Creator -> 50 characters allowed
        wallet.subscription_tier = 'creator'
        wallet.save()
        self.assertEqual(wallet.max_characters, 50)
        self.assertEqual(wallet.max_parallel_videos, 3)
        self.assertEqual(wallet.max_parallel_images, 4)

    def test_provider_diagnostics_operational_vs_unfunded(self):
        """Verify Kling, MiniMax, and OpenAI diagnostics report operational on HTTP 200 and unfunded on billing codes."""
        from unittest.mock import patch, MagicMock
        from apps.providers.diagnostics import ProviderHealthChecker

        with patch('apps.providers.diagnostics._resolve_api_key', return_value='test_key'):
            with patch('apps.providers.diagnostics.httpx.Client') as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value.__enter__.return_value = mock_client

                # HTTP 200 healthy response for Kling & OpenAI
                ok_resp = MagicMock(status_code=200, content=b'{"code": 0}')
                ok_resp.json.return_value = {'code': 0}
                mock_client.get.return_value = ok_resp

                kling_res = ProviderHealthChecker.check_kling_ai()
                self.assertEqual(kling_res['status'], 'operational')

                openai_res = ProviderHealthChecker.check_openai()
                self.assertEqual(openai_res['status'], 'operational')

                # Kling code 1102 -> unfunded
                unfunded_kling = MagicMock(status_code=400, content=b'{"code": 1102}')
                unfunded_kling.json.return_value = {'code': 1102, 'message': 'Account balance insufficient'}
                mock_client.get.return_value = unfunded_kling
                self.assertEqual(ProviderHealthChecker.check_kling_ai()['status'], 'unfunded')

                # MiniMax HTTP 200 with status_code 0 -> operational
                mm_ok = MagicMock(status_code=200, content=b'{"base_resp": {"status_code": 0}}')
                mm_ok.json.return_value = {'base_resp': {'status_code': 0, 'status_msg': 'success'}}
                mock_client.get.return_value = mm_ok
                self.assertEqual(ProviderHealthChecker.check_minimax()['status'], 'operational')

                # MiniMax status_code 1008 -> unfunded
                mm_unfunded = MagicMock(status_code=200, content=b'{"base_resp": {"status_code": 1008}}')
                mm_unfunded.json.return_value = {'base_resp': {'status_code': 1008, 'status_msg': 'insufficient balance'}}
                mock_client.get.return_value = mm_unfunded
                self.assertEqual(ProviderHealthChecker.check_minimax()['status'], 'unfunded')



