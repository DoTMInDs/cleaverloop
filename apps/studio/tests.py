from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User
from apps.credits.services import CreditService

class HomeAndDashboardViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='creator@cleaverloop.ai',
            username='creator',
            password='testpassword123'
        )
        self.wallet = CreditService.get_or_create_wallet(self.user)

    def test_homepage_renders_dedicated_landing_page(self):
        # Dedicated Homepage should be accessible at root / without redirecting to login
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')
        content = response.content.decode('utf-8')
        self.assertIn('Turn your imagination into', content)
        self.assertIn('cinematic reality', content)
        self.assertIn('Vintage Cartoon (1930s)', content)
        self.assertIn('Unhinged Cartoon', content)
        self.assertIn('Cozy Claymation', content)
        self.assertIn('Consistent Character Engine', content)
        self.assertIn('Super Agent Storyboard Director', content)
        self.assertIn('Start Creating Free (500 Credits)', content)

    def test_dashboard_redirects_anonymous_user_to_login(self):
        # Studio dashboard requires authentication
        response = self.client.get(reverse('studio:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_dashboard_renders_for_authenticated_user(self):
        self.client.login(email='creator@cleaverloop.ai', password='testpassword123')
        response = self.client.get(reverse('studio:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'studio/dashboard.html')
        content = response.content.decode('utf-8')
        self.assertIn('Studio Dashboard', content)
        self.assertIn('Creative Projects', content)
        self.assertIn('AI Characters', content)

    def test_local_offline_scripts_served(self):
        """Verify that HTMX and Alpine.js are served locally from static files and not from unpkg CDN."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Verify local vendor static script links exist
        self.assertIn('/static/js/vendor/htmx.min.js', content)
        self.assertIn('/static/js/vendor/alpine.min.js', content)
        
        # Verify unpkg CDN is no longer referenced
        self.assertNotIn('unpkg.com/htmx', content)
        self.assertNotIn('unpkg.com/alpinejs', content)
