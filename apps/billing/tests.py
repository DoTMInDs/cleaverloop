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
            price_monthly=15.00,
            credits_per_month=3000,
            features=["Access to Character builder", "Up to 5 custom characters"],
            max_parallel_videos=2,
            max_parallel_images=2,
            is_active=True
        )
        self.creator_plan = SubscriptionPlan.objects.create(
            name="Creator",
            slug="creator",
            price_monthly=45.00,
            credits_per_month=10000,
            tagline="For creators making real AI videos",
            badge_text="MOST POPULAR",
            features=["Full access to all models", "Up to 15 custom characters"],
            can_access_premium_models=True,
            max_parallel_videos=3,
            max_parallel_images=4,
            is_active=True
        )
        self.ultra_plan = SubscriptionPlan.objects.create(
            name="Ultra",
            slug="ultra",
            price_monthly=75.00,
            credits_per_month=25000,
            tagline="For creators building AI projects",
            badge_text="BEST VALUE",
            features=["Unlimited custom characters", "4K Rendering"],
            can_access_premium_models=True,
            max_parallel_videos=8,
            max_parallel_images=8,
            is_active=True
        )

    def test_pricing_page_renders_exact_tiers_and_comparison_table(self):
        """Verify the pricing page renders $15, $45, $75 cards, 500 free credits, and comparison matrix."""
        response = self.client.get(reverse('billing:plans'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Check pricing and credits
        self.assertIn("$15", content)
        self.assertIn("3000 credits/mo", content)
        self.assertIn("$45", content)
        self.assertIn("10000 credits/mo", content)
        self.assertIn("$75", content)
        self.assertIn("25000 credits/mo", content)
        self.assertIn("500 Starter Credits", content)

        # Check badges
        self.assertIn("MOST POPULAR", content)
        self.assertIn("BEST VALUE", content)

        # Check comparison table
        self.assertIn("Compare every plan", content)
        self.assertIn("Unlimited & free Veo 3.1 + Fast generations", content)
        self.assertIn("Parallel generations", content)
        self.assertIn("Character builder", content)

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
        """Verify returning from Paystack grants monthly credits and marks subscription active."""
        self.client.force_login(self.user)
        initial_balance = self.wallet.balance
        ref = "mock_ref_test_success_123"

        response = self.client.get(f"{reverse('billing:callback')}?reference={ref}&plan_id={self.creator_plan.id}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('billing:portal'))

        self.wallet.refresh_from_db()
        # Verify 10,000 credits granted
        self.assertEqual(self.wallet.balance, initial_balance + 10000)

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
        self.assertIn("Active Plan", content)
        self.assertIn("Current Balance", content)

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
        self.assertEqual(self.wallet.balance, initial_balance + 10000)

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
