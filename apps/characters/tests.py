from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User
from apps.characters.models import Character

class CharacterCRUDTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="creator@cleaverloop.ai", username="creator", password="password123")
        self.other_user = User.objects.create_user(email="other@cleaverloop.ai", username="other", password="password123")
        self.client = Client()
        self.client.force_login(self.user)
        self.character = Character.objects.create(
            owner=self.user,
            name="Maya Chen",
            appearance_description="Sharp jawline, raven hair",
            clothing_description="Cyberpunk jacket"
        )

    def test_character_update(self):
        """Verify user can update their own character."""
        url = reverse('characters:edit', kwargs={'pk': self.character.pk})
        resp = self.client.post(url, {
            'name': 'Maya Chen Updated',
            'appearance_description': 'Sharp jawline, raven hair, cybernetic eye',
            'clothing_description': 'Neon hoodie',
        })
        self.assertEqual(resp.status_code, 302)
        self.character.refresh_from_db()
        self.assertEqual(self.character.name, 'Maya Chen Updated')
        self.assertEqual(self.character.clothing_description, 'Neon hoodie')

    def test_character_delete(self):
        """Verify user can delete their own character."""
        url = reverse('characters:delete', kwargs={'pk': self.character.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Character.objects.filter(pk=self.character.pk).exists())

    def test_character_cross_user_update_blocked(self):
        """Verify user cannot update another user's character."""
        self.client.force_login(self.other_user)
        url = reverse('characters:edit', kwargs={'pk': self.character.pk})
        resp = self.client.post(url, {'name': 'Hacked'})
        self.assertEqual(resp.status_code, 404)
