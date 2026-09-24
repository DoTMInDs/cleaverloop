import json
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from apps.accounts.models import User
from apps.billing.models import SubscriptionPlan, Subscription
from apps.credits.models import CreditWallet, CreditTransaction
from apps.credits.services import CreditService

@override_settings(PAYMENT_PROVIDER='mock', PAYSTACK_SECRET_KEY='')
class PaystackBillingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="creator@cleaverloop.ai",
            username="creator",
            password="securepassword123"
        )
        self.wallet = CreditService.get_or_create_wallet(self.user)

        self.free_plan = SubscriptionPlan.objects.create(
            name="Free Starter",
            slug="free-starter",
            price_monthly=0.00,
            credits_per_month=500,
            features=["500 Starter Credits", "Access to Standard Models"],
            is_active=True
        )
        self.starter_plan = SubscriptionPlan.objects.create(
            name="Starter",
            slug="starter",
            price_monthly=19.00,
            credits_per_month=90000,
            features=["90,000 credits/mo", "Up to 5 custom characters"],
            max_parallel_videos=2,
            max_parallel_images=2,
            is_active=True
        )
        self.creator_plan = SubscriptionPlan.objects.create(
            name="Creator",
            slug="creator",
            price_monthly=59.00,
            credits_per_month=400000,
            tagline="For power creators producing viral stories & campaigns",
            badge_text="MOST POPULAR • UNLIMITED",
            features=["400,000 priority credits", "Unlimited Relaxed Generations"],
            can_access_premium_models=True,
            max_parallel_videos=4,
            max_parallel_images=4,
            is_active=True
        )
        self.ultra_plan = SubscriptionPlan.objects.create(
            name="Ultra / Pro",
            slug="ultra",
            price_monthly=129.00,
            credits_per_month=1000000,
            tagline="For studios, agencies, and high-velocity directors",
            badge_text="STUDIO PRO • BEST VALUE",
            features=["1,000,000 priority credits", "Unlimited Relaxed + VIP Instant GPU"],
            can_access_premium_models=True,
            max_parallel_videos=8,
            max_parallel_images=8,
            is_active=True
        )

    def test_pricing_page_renders_exact_tiers_and_comparison_table(self):
        """Verify the pricing page renders $19, $59, $129 cards, 500 free credits, and comparison matrix."""
        response = self.client.get(reverse('billing:plans'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Check pricing and credits
        self.assertIn("$19", content)
        self.assertIn("90,000", content)
        self.assertIn("$59", content)
        self.assertIn("400,000", content)
        self.assertIn("$129", content)
        self.assertIn("1,000,000", content)
        self.assertIn("500 Credits", content)

        # Check comparison table
        self.assertIn("Compare Plan Features", content)
        self.assertIn("Unlimited Relaxed Generations", content)
        self.assertIn("Parallel Generation Slots", content)

    def test_checkout_initialization_requires_login(self):
        """Verify anonymous user is redirected to login when attempting checkout."""
        response = self.client.post(reverse('billing:checkout', args=[self.creator_plan.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_checkout_initialization_redirects_to_paystack_url(self):
        """Verify authenticated checkout redirects to authorization URL."""
        self.client.force_login(self.user)
        response = self.client.post(reverse('billing:checkout', args=[self.creator_plan.id]))
        self.assertEqual(response.status_code, 302)
        # In mock mode, should redirect to callback with mock reference
        self.assertIn('callback', response.url)
        self.assertIn('reference=mock_ref_', response.url)

    def test_payment_callback_activates_subscription_and_grants_credits(self):
        """Verify returning from Paystack grants monthly credits, marks subscription active, and syncs wallet tier."""
        self.client.force_login(self.user)
        initial_balance = self.wallet.balance
        ref = "mock_ref_test_success_123"

        response = self.client.get(f"{reverse('billing:callback')}?reference={ref}&plan_id={self.creator_plan.id}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('billing:portal'))

        self.wallet.refresh_from_db()
        # Verify 400,000 credits granted and wallet tier set to creator
        self.assertEqual(self.wallet.balance, initial_balance + 400000)
        self.assertEqual(self.wallet.subscription_tier, 'creator')
        self.assertEqual(self.wallet.subscription_credits, 400000)

        # Verify active subscription
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.plan, self.creator_plan)
        self.assertEqual(sub.status, 'active')
        self.assertEqual(sub.last_payment_reference, ref)

    def test_idempotent_callback_prevents_duplicate_credits(self):
        """Verify duplicate callback visits do not double-grant credits."""
        self.client.force_login(self.user)
        ref = "mock_ref_idempotent_test"

        # First visit
        self.client.get(f"{reverse('billing:callback')}?reference={ref}&plan_id={self.creator_plan.id}")
        self.wallet.refresh_from_db()
        balance_after_first = self.wallet.balance

        # Second visit with same reference
        self.client.get(f"{reverse('billing:callback')}?reference={ref}&plan_id={self.creator_plan.id}")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, balance_after_first)

    def test_subscription_portal_view(self):
        """Verify customer portal renders active subscription and balance."""
        self.client.force_login(self.user)
        Subscription.objects.create(
            user=self.user,
            plan=self.creator_plan,
            status='active',
            last_payment_reference='ref_portal_test'
        )
        response = self.client.get(reverse('billing:portal'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn("Creator", content)
        self.assertIn("Active Subscription", content)
        self.assertIn("Available Balance", content)

    def test_cancel_subscription_flow(self):
        """Verify subscriber can cancel their subscription."""
        self.client.force_login(self.user)
        sub = Subscription.objects.create(
            user=self.user,
            plan=self.creator_plan,
            status='active',
            external_subscription_id='SUB_test_123',
            email_token='token_123'
        )
        response = self.client.post(reverse('billing:cancel'))
        self.assertEqual(response.status_code, 302)
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'canceled')

    def test_webhook_charge_success_event(self):
        """Verify incoming Paystack charge.success webhook awards credits."""
        webhook_payload = {
            "event": "charge.success",
            "data": {
                "reference": "paystack_webhook_ref_999",
                "amount": 4500,
                "customer": {
                    "email": self.user.email,
                    "customer_code": "CUS_test_999"
                },
                "metadata": {
                    "user_id": self.user.id,
                    "plan_id": self.creator_plan.id
                }
            }
        }
        initial_balance = self.wallet.balance
        response = self.client.post(
            reverse('billing:webhook'),
            data=json.dumps(webhook_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, initial_balance + 400000)
        self.assertEqual(self.wallet.subscription_tier, 'creator')


    @override_settings(PAYMENT_PROVIDER='paystack', PAYSTACK_SECRET_KEY='test_sk_secret_999')
    def test_live_mode_webhook_signature_enforcement(self):
        """Verify webhook signature HMAC SHA512 enforcement when in live Paystack mode."""
        import hmac, hashlib
        payload = json.dumps({"event": "charge.success", "data": {"reference": "signed_ref_1"}})
        
        # 1. Unsigned request rejected with 401
        res_unsigned = self.client.post(
            reverse('billing:webhook'),
            data=payload,
            content_type='application/json'
        )
        self.assertEqual(res_unsigned.status_code, 401)

        # 2. Correctly signed request accepted
        sig = hmac.new(b'test_sk_secret_999', payload.encode('utf-8'), hashlib.sha512).hexdigest()
        res_signed = self.client.post(
            reverse('billing:webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=sig
        )
        self.assertEqual(res_signed.status_code, 200)

    def test_payment_callback_blocks_idor_when_user_mismatch(self):
        """Red Team Test: Verify an attacker cannot hijack another customer's payment reference."""
        victim = User.objects.create_user(
            email="victim@cleaverloop.ai",
            username="victim",
            password="victimpassword"
        )
        CreditService.get_or_create_wallet(victim)

        # Initialize checkout as victim
        from apps.billing.paystack import PaystackService
        init_res = PaystackService.initialize_transaction(victim, self.ultra_plan, "http://testserver/billing/callback/")
        victim_ref = init_res['data']['reference']

        # Attacker logs in and attempts to claim victim's paid reference
        self.client.force_login(self.user)
        initial_attacker_bal = self.wallet.balance
        attacker_res = self.client.get(f"{reverse('billing:callback')}?reference={victim_ref}")

        # Must be rejected with redirect back to plans
        self.assertEqual(attacker_res.status_code, 302)
        self.assertEqual(attacker_res.url, reverse('billing:plans'))

        # Attacker's wallet must NOT receive ultra tier or credits
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, initial_attacker_bal)
        self.assertNotEqual(self.wallet.subscription_tier, 'ultra')

    def test_topup_credit_grant_cannot_be_tampered_via_query_params(self):
        """Red Team Test: Verify client-side query parameters cannot inflate top-up credit amounts."""
        self.client.force_login(self.user)
        initial_balance = self.wallet.balance

        from apps.billing.paystack import PaystackService
        init_res = PaystackService.initialize_topup_transaction(
            user=self.user,
            pack_id='pack-50k',
            credits_amount=50000,
            price_usd=10.00,
            callback_url="http://testserver/billing/callback/"
        )
        ref = init_res['data']['reference']

        # Malicious user tampers with URL trying to request 10 million credits
        tampered_url = f"{reverse('billing:callback')}?reference={ref}&topup_credits=10000000"
        res = self.client.get(tampered_url)
        self.assertEqual(res.status_code, 302)

        # Wallet must strictly receive the authentic pack amount (50,000), not the tampered query value
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, initial_balance + 50000)

    def test_duplicate_external_reference_db_constraint(self):
        """Verify DB-level unique constraint prevents duplicate external_references, but allows multiple empty references."""
        from django.db import IntegrityError, transaction
        # 1. First transaction with ref succeeds
        CreditTransaction.objects.create(
            wallet=self.wallet,
            amount=100,
            transaction_type='bonus',
            balance_before=0,
            balance_after=100,
            description='Test Ref 1',
            external_reference='paystack:unique_test_ref_1'
        )

        # 2. Second transaction with identical ref must raise IntegrityError inside a savepoint
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                CreditTransaction.objects.create(
                    wallet=self.wallet,
                    amount=100,
                    transaction_type='bonus',
                    balance_before=100,
                    balance_after=200,
                    description='Test Ref 1 Duplicate',
                    external_reference='paystack:unique_test_ref_1'
                )

        # 3. Multiple empty external_reference values are allowed
        CreditTransaction.objects.create(
            wallet=self.wallet,
            amount=50,
            transaction_type='adjustment',
            balance_before=100,
            balance_after=150,
            description='Empty ref 1',
            external_reference=''
        )
        CreditTransaction.objects.create(
            wallet=self.wallet,
            amount=50,
            transaction_type='adjustment',
            balance_before=150,
            balance_after=200,
            description='Empty ref 2',
            external_reference=''
        )

    def test_webhook_handles_invoice_payment_failed(self):
        """Verify failed renewal invoice marks active subscription as past_due."""
        sub = Subscription.objects.create(
            user=self.user,
            plan=self.creator_plan,
            status='active',
            external_subscription_id='SUB_pay_fail_test'
        )
        webhook_payload = {
            "event": "invoice.payment_failed",
            "data": {
                "subscription_code": "SUB_pay_fail_test",
                "customer": {
                    "email": self.user.email
                }
            }
        }
        res = self.client.post(
            reverse('billing:webhook'),
            data=json.dumps(webhook_payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'past_due')
