from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.characters.models import Character, SceneAsset
from apps.credits.services import CreditService

User = get_user_model()


class CharacterWorldAssetsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='worldbuilder',
            email='world@example.com',
            password='password123'
        )
        self.wallet = CreditService.get_or_create_wallet(self.user)
        self.wallet.subscription_tier = 'creator'
        self.wallet.save(update_fields=['subscription_tier'])
        self.client.force_login(self.user)

        self.base_char = Character.objects.create(
            owner=self.user,
            name='Kofi Mensah',
            appearance_description='Tall athletic build, sharp jawline, warm brown eyes',
            clothing_description='Charcoal linen suit',
            universe_style='cinematic',
        )

    def test_create_character_variant_preserves_face_dna_and_sets_variant_fields(self):
        resp = self.client.post(
            reverse('characters:create_variant', kwargs={'pk': self.base_char.pk}),
            {
                'variant_label': 'Tactical Exo-Suit',
                'clothing_description': 'Matte black orbital armor with amber HUD visor',
                'universe_style': 'cyberpunk',
            }
        )
        self.assertEqual(resp.status_code, 302)
        variant = Character.objects.filter(parent_character=self.base_char).first()
        self.assertIsNotNone(variant)
        self.assertEqual(variant.variant_label, 'Tactical Exo-Suit')
        self.assertEqual(variant.universe_style, 'cyberpunk')
        self.assertEqual(variant.appearance_description, self.base_char.appearance_description)
        cue = variant.build_prompt_cue()
        self.assertIn('Variant: Tactical Exo-Suit', cue)
        self.assertIn('Style Universe: Cyberpunk', cue)

    def test_create_character_variant_enforces_tier_character_limit(self):
        self.wallet.subscription_tier = 'free'
        self.wallet.save(update_fields=['subscription_tier'])
        # Free tier allows max 1 character, and self.base_char already exists
        resp = self.client.post(
            reverse('characters:create_variant', kwargs={'pk': self.base_char.pk}),
            {'variant_label': 'Blocked Variant'}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Character.objects.filter(owner=self.user).count(), 1)

    def test_create_and_delete_location_and_element_scene_assets(self):
        # Create Location
        resp_loc = self.client.post(
            reverse('characters:create_asset'),
            {
                'asset_type': 'location',
                'name': 'Neo-Accra Skyport',
                'category': 'Sci-Fi Exterior',
                'universe_style': 'cyberpunk',
                'time_of_day': 'Midnight',
                'weather': 'Neon Rain',
                'description': 'Brutalist concrete landing pad with holographic billboards',
            }
        )
        self.assertEqual(resp_loc.status_code, 302)
        loc = SceneAsset.objects.filter(owner=self.user, asset_type='location').first()
        self.assertIsNotNone(loc)
        self.assertIn('Time of Day: Midnight', loc.build_prompt_cue())
        self.assertIn('Weather/Atmosphere: Neon Rain', loc.build_prompt_cue())

        # Create Element
        resp_el = self.client.post(
            reverse('characters:create_asset'),
            {
                'asset_type': 'element',
                'name': 'Solaris Relic Blade',
                'category': 'Artifact',
                'universe_style': 'anime',
                'description': 'Translucent golden katana with etched solar runes',
            }
        )
        self.assertEqual(resp_el.status_code, 302)
        el = SceneAsset.objects.filter(owner=self.user, asset_type='element').first()
        self.assertIsNotNone(el)
        self.assertIn('Solaris Relic Blade', el.build_prompt_cue())

        # List view includes both locations and elements
        list_resp = self.client.get(reverse('characters:list'))
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.context['locations']), 1)
        self.assertEqual(len(list_resp.context['elements']), 1)

        # Delete Location
        del_resp = self.client.post(reverse('characters:delete_asset', kwargs={'asset_id': loc.id}))
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(SceneAsset.objects.filter(id=loc.id).exists())

    def test_generate_turnaround_sheet_locks_360_angles_and_expressions(self):
        resp = self.client.post(
            reverse('characters:generate_turnaround', kwargs={'pk': self.base_char.pk})
        )
        self.assertEqual(resp.status_code, 302)
        self.base_char.refresh_from_db()
        self.assertTrue(self.base_char.metadata.get('turnaround_forged'))
        angles = self.base_char.get_turnaround_angles()
        self.assertEqual(len(angles), 4)
        self.assertEqual(angles[0]['id'], 'front_ortho')
        expressions = self.base_char.get_expressions()
        self.assertEqual(len(expressions), 4)
        self.assertEqual(expressions[0]['id'], 'neutral')
