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

    def test_generate_ai_from_text(self):
        """Verify text brief character synthesis endpoint."""
        url = reverse('characters:generate_ai')
        resp = self.client.post(url, {
            'brief': 'A futuristic cyberpunk bounty hunter with neon orange hair',
            'style_preset': 'cyberpunk'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('name', data)
        self.assertIn('appearance_description', data)
        self.assertIn('avatar_url', data)

    def test_generate_ai_from_photo(self):
        """Verify photo face upload triggers multimodal character synthesis."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        # 1x1 dummy PNG image
        png_bytes = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff'
            b'?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        photo = SimpleUploadedFile("face.png", png_bytes, content_type="image/png")
        url = reverse('characters:generate_ai')
        resp = self.client.post(url, {
            'photo': photo,
            'style_preset': 'cinematic',
            'brief': 'Lead protagonist'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('name', data)
        self.assertIn('appearance_description', data)
        self.assertIn('avatar_url', data)
        self.assertTrue('characters/avatars/face_' in data['avatar_url'])

    def test_generate_ai_invalid_file_type(self):
        """Verify non-image file uploads are rejected."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad_file = SimpleUploadedFile("script.txt", b"not an image", content_type="text/plain")
        url = reverse('characters:generate_ai')
        resp = self.client.post(url, {
            'photo': bad_file,
            'style_preset': 'cinematic'
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Unsupported image format', resp.json().get('error', ''))
