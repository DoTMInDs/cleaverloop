from django.test import TestCase, Client
from apps.accounts.models import User
from apps.providers.models import AIProviderConfig, AIModel
from apps.providers.registry import ModelRegistry

class AdminPanelSecurityTests(TestCase):
    def setUp(self):
        ModelRegistry.seed_initial_catalog()
        self.staff_user = User.objects.create_user(
            email="staff@cleverloop.ai",
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
