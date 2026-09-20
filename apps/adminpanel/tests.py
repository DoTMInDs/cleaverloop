from django.test import TestCase, Client
from apps.accounts.models import User
from apps.providers.models import AIProviderConfig, AIModel
from apps.providers.registry import ModelRegistry

class AdminPanelSecurityTests(TestCase):
    def setUp(self):
        ModelRegistry.seed_initial_catalog()
        self.staff_user = User.objects.create_user(
            email="staff@cleaverloop.ai",
            username="staffuser",
            password="password123",
            is_staff=True
        )
        self.client = Client()
        self.client.force_login(self.staff_user)
        self.model = AIModel.objects.first()

    def test_get_request_to_toggle_model_rejected_csrf_protection(self):
        """Verify GET requests to toggle_model_status_view return 405 (CSRF protection)."""
        initial_status = self.model.is_enabled
        resp = self.client.get(f"/adminpanel/models/{self.model.id}/toggle/")
        self.assertEqual(resp.status_code, 405)  # Method Not Allowed!
        self.model.refresh_from_db()
        self.assertEqual(self.model.is_enabled, initial_status)  # State unchanged!

    def test_post_request_to_toggle_model_succeeds(self):
        """Verify POST requests toggle model successfully."""
        initial_status = self.model.is_enabled
        resp = self.client.post(f"/adminpanel/models/{self.model.id}/toggle/")
        self.assertEqual(resp.status_code, 302)
        self.model.refresh_from_db()
        self.assertNotEqual(self.model.is_enabled, initial_status)

    def test_save_new_plan_via_admin(self):
        """Verify staff can create a new pricing plan with custom figures and features."""
        from apps.billing.models import SubscriptionPlan
        data = {
            'name': 'Studio Growth',
            'slug': 'studio-growth',
            'price_monthly': '49.00',
            'credits_per_month': '8000',
            'max_parallel_generations': '3',
            'can_access_premium_models': 'on',
            'is_active': 'on',
            'features_raw': '8,000 Credits / month\nPriority 4K Queue\nDedicated GPUs'
        }
        resp = self.client.post("/adminpanel/plans/save/", data=data)
        self.assertEqual(resp.status_code, 302)

        plan = SubscriptionPlan.objects.get(slug='studio-growth')
        self.assertEqual(plan.name, 'Studio Growth')
        self.assertEqual(plan.price_monthly, 49.00)
        self.assertEqual(plan.credits_per_month, 8000)
        self.assertEqual(len(plan.features), 3)
        self.assertEqual(plan.features[0], '8,000 Credits / month')
        self.assertTrue(plan.can_access_premium_models)
        self.assertTrue(plan.is_active)

    def test_update_existing_plan_via_admin(self):
        """Verify staff can edit existing plan figures (price, credits, etc.)."""
        from apps.billing.models import SubscriptionPlan
        plan = SubscriptionPlan.objects.create(
            name='Starter Test',
            slug='starter-test',
            price_monthly=0,
            credits_per_month=500,
            features=['500 Starter Credits']
        )
        data = {
            'plan_id': plan.id,
            'name': 'Starter Test Updated',
            'slug': 'starter-test',
            'price_monthly': '10.00',
            'credits_per_month': '1200',
            'max_parallel_generations': '2',
            'features_raw': '1,200 Credits / month\nAccess to all standard tools'
        }
        resp = self.client.post("/adminpanel/plans/save/", data=data)
        self.assertEqual(resp.status_code, 302)

        plan.refresh_from_db()
        self.assertEqual(plan.name, 'Starter Test Updated')
        self.assertEqual(plan.price_monthly, 10.00)
        self.assertEqual(plan.credits_per_month, 1200)
        self.assertEqual(len(plan.features), 2)

    def test_toggle_plan_status(self):
        """Verify staff can enable/disable plans."""
        from apps.billing.models import SubscriptionPlan
        plan = SubscriptionPlan.objects.create(
            name='Toggle Plan',
            slug='toggle-plan',
            price_monthly=15,
            credits_per_month=1000,
            is_active=True
        )
        resp = self.client.post(f"/adminpanel/plans/{plan.id}/toggle/")
        self.assertEqual(resp.status_code, 302)
        plan.refresh_from_db()
        self.assertFalse(plan.is_active)

    def test_update_starter_credits_config(self):
        """Verify staff can adjust default welcome credits for new users."""
        from apps.billing.models import SubscriptionPlan
        free_plan = SubscriptionPlan.objects.create(
            name='Free Starter',
            slug='free-starter',
            price_monthly=0,
            credits_per_month=500,
            features=['500 Starter Credits', 'Access to Standard Models']
        )
        resp = self.client.post("/adminpanel/credits/starter-amount/", data={'starter_credits': '750'})
        self.assertEqual(resp.status_code, 302)

        free_plan.refresh_from_db()
        self.assertEqual(free_plan.credits_per_month, 750)
        self.assertEqual(free_plan.features[0], '750 Starter Credits')

        # Now test that a new user gets 750 starter credits
        new_user = User.objects.create_user(
            email="newcreator@cleaverloop.ai",
            username="newcreator",
            password="securepassword123"
        )
        from apps.credits.services import CreditService
        wallet = CreditService.get_or_create_wallet(new_user)
        self.assertEqual(wallet.balance, 750)

    def test_non_staff_cannot_modify_plans(self):
        """Verify non-staff users cannot access plan modification endpoints."""
        regular_user = User.objects.create_user(
            email="regular@cleaverloop.ai",
            username="regularuser",
            password="password123",
            is_staff=False
        )
        self.client.force_login(regular_user)
        resp = self.client.post("/adminpanel/plans/save/", data={'name': 'Hacked Plan'})
        # Should be redirected to admin login
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_adjust_user_credits_grant_and_deduct(self):
        """Verify staff can grant and deduct user credits safely."""
        from apps.credits.services import CreditService
        target_user = User.objects.create_user(
            email="target@cleaverloop.ai",
            username="targetuser",
            password="password123"
        )
        wallet = CreditService.get_or_create_wallet(target_user)
        initial_balance = wallet.balance

        # 1. Grant +300
        self.client.post("/adminpanel/credits/adjust/", data={
            'user_email': target_user.email,
            'amount': '300',
            'reason': 'Bonus for testing'
        })
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance + 300)

        # 2. Deduct -150
        self.client.post("/adminpanel/credits/adjust/", data={
            'user_email': target_user.email,
            'amount': '-150',
            'reason': 'Correction'
        })
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance + 150)

    def test_quick_refill_forbidden_for_regular_users_in_production(self):
        """Verify regular users cannot invoke /credits/quick-refill/ when DEBUG=False."""
        from django.test import override_settings
        regular_user = User.objects.create_user(
            email="regular2@cleaverloop.ai",
            username="regular2",
            password="password123",
            is_staff=False
        )
        self.client.force_login(regular_user)
        with override_settings(DEBUG=False):
            resp = self.client.post('/credits/quick-refill/')
            self.assertEqual(resp.status_code, 403)
