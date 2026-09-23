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

    def test_generate_ai_primary_face_isolation_and_full_body_regeneration(self):
        """Verify multi-person disambiguation, smart face isolation, and full-body regeneration."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        # Create a valid 200x300 image
        img = Image.new('RGB', (200, 300), color=(180, 80, 40))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        photo = SimpleUploadedFile("group_photo.jpg", buffer.getvalue(), content_type="image/jpeg")

        url = reverse('characters:generate_ai')
        resp = self.client.post(url, {
            'photo': photo,
            'style_preset': 'cinematic',
            'brief': 'Scholar at library with braids'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('name', data)
        self.assertIn('appearance_description', data)
        self.assertIn('clothing_description', data)
        self.assertIn('avatar_url', data)
        self.assertTrue('characters/avatars/face_isolated_' in data['avatar_url'])
        self.assertIn('subject_isolation', data)
        self.assertTrue(len(data['subject_isolation']) > 0)
        self.assertIn('full_body_prompt', data)
        self.assertIn('poses', data)
        self.assertTrue(len(data['poses']) >= 1)
        standing_pose = next((p for p in data['poses'] if p.get('id') == 'standing'), None)
        self.assertIsNotNone(standing_pose)

    def test_generate_ai_from_prompt_exact_specifics(self):
        """Verify prompt character forge adheres strictly to user's exact prompt specifics and feminine real-life posing."""
        url = reverse('characters:generate_ai')
        resp = self.client.post(url, {
            'brief': '24-year-old Scandinavian female interior designer named Astrid Lindholm with platinum blonde hair in loose low ponytail, hazel eyes, wearing an oversized cream knit cardigan over olive linen trousers and white canvas sneakers, standing with relaxed confident posture',
            'style_preset': 'cinematic'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('name'), 'Astrid Lindholm')
        self.assertEqual(data.get('gender'), 'female')
        self.assertIn('feminine silhouette', data.get('body_type', '').lower())
        self.assertIn('cardigan', data.get('clothing_description', '').lower())
        self.assertIn('contrapposto', data.get('full_body_prompt', '').lower())
        self.assertIn('poses', data)
        self.assertEqual(len(data['poses']), 3)
        standing_pose = next((p for p in data['poses'] if p.get('id') == 'standing'), None)
        self.assertIsNotNone(standing_pose)
        self.assertIn('contrapposto', standing_pose.get('label', '').lower() + standing_pose.get('prompt_cue', '').lower())

