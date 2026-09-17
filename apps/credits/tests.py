from django.test import TestCase, TransactionTestCase
from apps.accounts.models import User
from apps.credits.models import CreditWallet, CreditTransaction
from apps.credits.services import CreditService, InsufficientCreditsError
from apps.generations.models import Generation
from apps.providers.models import AIProviderConfig, AIModel

class CreditLedgerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="test@cleverloop.ai", username="testuser", password="password123")
        self.provider = AIProviderConfig.objects.create(slug="mock", name="Mock Provider")
        self.model = AIModel.objects.create(
            provider=self.provider,
            model_id="mock-model",
            display_name="Mock Model",
            modality="video",
            credit_cost_fixed=50,
            credit_cost_per_second=25
        )

    def test_starter_credits_granted_on_user_creation(self):
        """Verify new users automatically receive starter credits and a CreditWallet."""
        wallet = CreditWallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 500)
        self.assertEqual(wallet.lifetime_earned, 500)
        self.assertEqual(wallet.transactions.count(), 1)
        self.assertEqual(wallet.transactions.first().transaction_type, 'bonus')

    def test_atomic_reservation_and_commit(self):
        """Verify credits are reserved and committed accurately."""
        wallet = CreditWallet.objects.get(user=self.user)
        initial_balance = wallet.balance

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.model,
            model_id_snapshot=self.model.model_id,
            prompt="Test prompt",
            duration=5
        )

        cost = self.model.calculate_credit_cost(duration=5)  # 50 + 5*25 = 175
        CreditService.reserve_credits(self.user, cost, gen)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance - 175)
        self.assertEqual(gen.credits_reserved, 175)

        # Commit credits
        CreditService.commit_credits(gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance - 175)
        self.assertEqual(wallet.lifetime_spent, 175)
        self.assertEqual(gen.credits_consumed, 175)

    def test_reservation_failure_insufficient_credits(self):
        """Verify InsufficientCreditsError is raised if wallet balance is too low."""
        wallet = CreditWallet.objects.get(user=self.user)
        wallet.balance = 20
        wallet.save()

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.model,
            model_id_snapshot=self.model.model_id,
            prompt="Test prompt",
            duration=5
        )

        with self.assertRaises(InsufficientCreditsError):
            CreditService.reserve_credits(self.user, 100, gen)

    def test_refund_on_failure_restores_balance(self):
        """Verify reserved credits are fully refunded on job failure."""
        wallet = CreditWallet.objects.get(user=self.user)
        initial_balance = wallet.balance

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.model,
            model_id_snapshot=self.model.model_id,
            prompt="Test prompt",
            duration=5
        )

        CreditService.reserve_credits(self.user, 200, gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance - 200)

        # Refund
        CreditService.refund_credits(gen, reason="Provider timeout")
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance)
        self.assertEqual(gen.credits_reserved, 0)

    def test_double_refund_prevented_idempotency(self):
        """Verify calling refund_credits multiple times on the same generation only refunds once."""
        wallet = CreditWallet.objects.get(user=self.user)
        initial_balance = wallet.balance

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=self.provider,
            model=self.model,
            model_id_snapshot=self.model.model_id,
            prompt="Test prompt",
            duration=5
        )

        CreditService.reserve_credits(self.user, 150, gen)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance - 150)

        # First refund
        tx1 = CreditService.refund_credits(gen, reason="Failure 1")
        self.assertIsNotNone(tx1)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance)

        # Duplicate refund call must return None and not double-credit wallet
        tx2 = CreditService.refund_credits(gen, reason="Failure 2 (Duplicate)")
        self.assertIsNone(tx2)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance)
