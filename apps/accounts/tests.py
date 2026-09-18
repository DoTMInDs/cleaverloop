from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User
from apps.credits.services import CreditService
from apps.accounts.views import generate_user_referral_code

class ProfileViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='essetech3@gmail.com',
            username='esse tech',
            password='testpassword123'
        )
        self.wallet = CreditService.get_or_create_wallet(self.user)

    def test_profile_redirects_for_anonymous(self):
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 302)

    def test_profile_renders_successfully_for_authenticated(self):
        self.client.login(email='essetech3@gmail.com', password='testpassword123')
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/profile.html')
        
        # Check context
        self.assertIn('referral_code', response.context)
        self.assertIn('referral_code_spaced', response.context)
        self.assertIn('plan_name', response.context)
        self.assertEqual(response.context['plan_name'], 'Free')

        # Check template contents
        content = response.content.decode('utf-8')
        self.assertIn('esse tech', content)
        self.assertIn('essetech3@gmail.com', content)
        self.assertIn('CREDITS', content)
        self.assertIn('SUBSCRIPTION', content)
        self.assertIn('REFER & EARN', content)
        self.assertIn('ACCOUNT', content)
        self.assertIn('Invite friends, earn credits', content)
        self.assertIn('Share on TikTok', content)
        self.assertIn('Contact Support', content)
        self.assertIn('Privacy Policy', content)
        self.assertIn('Terms of Service', content)
        self.assertIn('Sign Out', content)

    def test_referral_code_generation(self):
        code1 = generate_user_referral_code(self.user)
        code2 = generate_user_referral_code(self.user)
        self.assertEqual(code1, code2)
        self.assertEqual(len(code1), 6)
        self.assertTrue(code1.isupper())

class AuthViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_login_view_renders_oauth_buttons_and_carousel(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')
        content = response.content.decode('utf-8')
        self.assertIn('Welcome back', content)
        self.assertIn('Continue with Google', content)
        self.assertIn('Continue with Apple', content)
        self.assertIn('Continue with Email', content)
        self.assertIn('OLD CARTOON STYLE', content)
        self.assertIn('EVERYDAY LIFE', content)
        self.assertIn('Old Cartoon', content)
        # Verify navbar is excluded
        self.assertNotIn('credit-badge-container', content)
        self.assertNotIn('Quick Navigation (Desktop)', content)
        self.assertNotIn('Bottom Navigation Bar for Mobile', content)

    def test_register_view_renders_oauth_buttons_and_carousel(self):
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')
        content = response.content.decode('utf-8')
        self.assertIn('Welcome to CleaverLoop', content)
        self.assertIn('Continue with Google', content)
        self.assertIn('Continue with Apple', content)
        self.assertIn('Continue with Email', content)
        self.assertIn('OLD CARTOON STYLE', content)
        self.assertIn('EVERYDAY LIFE', content)
        # Verify navbar is excluded
        self.assertNotIn('credit-badge-container', content)
        self.assertNotIn('Quick Navigation (Desktop)', content)
        self.assertNotIn('Bottom Navigation Bar for Mobile', content)

    def test_authenticated_profile_renders_navbar_from_partial(self):
        user = User.objects.create_user(email='profile_nav@cleaverloop.ai', username='navuser', password='password123')
        self.client.login(email='profile_nav@cleaverloop.ai', password='password123')
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('credit-badge-container', content)
        self.assertIn('Quick Navigation (Desktop)', content)

    def test_oauth_login_urls_resolve(self):
        google_url = reverse('google_login')
        self.assertEqual(google_url, '/accounts/google/login/')
        apple_url = reverse('apple_login')
        self.assertEqual(apple_url, '/accounts/apple/login/')

    def test_ajax_login_success(self):
        User.objects.create_user(email='ajax_user@cleaverloop.ai', username='ajax_user', password='validpassword123')
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'ajax_user@cleaverloop.ai', 'password': 'validpassword123'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIn('redirect_url', data)

    def test_ajax_login_failure(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'invalid@cleaverloop.ai', 'password': 'wrongpassword'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('error_message', data)

    def test_ajax_register_success(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'email': 'new_ajax_creator@cleaverloop.ai',
                'username': 'new_creator',
                'password1': 'StrongPass12345!',
                'password2': 'StrongPass12345!'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIn('redirect_url', data)
        self.assertTrue(User.objects.filter(email='new_ajax_creator@cleaverloop.ai').exists())


