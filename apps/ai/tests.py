import json
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.ai.models import AgentConversation, AgentMessage, ViralEffectTemplate
from apps.credits.services import CreditService
from apps.providers.models import AIProviderConfig, AIModel
from apps.generations.models import Generation

User = get_user_model()


class SuperAgentAndViralEffectsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='agentdirector',
            email='director@example.com',
            password='password123',
        )
        self.wallet = CreditService.get_or_create_wallet(self.user)
        self.wallet.subscription_tier = 'creator'
        self.wallet.balance = 50000
        self.wallet.save(update_fields=['subscription_tier', 'balance'])
        self.client.force_login(self.user)

        self.provider, _ = AIProviderConfig.objects.get_or_create(
            slug='google-veo',
            defaults={'name': 'Google Veo', 'is_enabled': True},
        )
        self.video_model, _ = AIModel.objects.get_or_create(
            model_id='veo-3.1-fast',
            defaults={
                'provider': self.provider,
                'display_name': 'Veo 3.1 Fast',
                'modality': 'video',
                'is_enabled': True,
                'credit_cost_fixed': 50,
                'credit_cost_per_second': 20,
            },
        )

    def test_plan_agent_brief_creates_conversation_with_skill_and_clarifications(self):
        resp = self.client.post(
            reverse('agent:plan'),
            {
                'prompt': 'A neon cyberpunk samurai duel on a rain-slicked rooftop',
                'aspect_ratio': '9:16',
                'skill_preset': 'viral_reel',
                'visual_tone': 'High-Contrast Neon & Anamorphic Glow',
                'pacing_style': 'Fast Kinetic Cuts & FPV Whip Pans',
            },
        )
        self.assertEqual(resp.status_code, 200)
        conv = AgentConversation.objects.filter(user=self.user).first()
        self.assertIsNotNone(conv)
        self.assertEqual(conv.skill_preset, 'viral_reel')
        self.assertEqual(conv.status, 'planned')
        self.assertEqual(conv.clarifying_answers.get('visual_tone'), 'High-Contrast Neon & Anamorphic Glow')
        self.assertEqual(AgentMessage.objects.filter(conversation=conv).count(), 2)

    @patch('apps.ai.views.dispatch_generation_task.delay')
    def test_execute_agent_plan_links_project_to_conversation(self, mock_delay):
        plan_resp = self.client.post(
            reverse('agent:plan'),
            {
                'prompt': 'A luxury watch commercial in macro golden hour lighting',
                'aspect_ratio': '16:9',
                'skill_preset': 'commercial_ad',
            },
        )
        self.assertEqual(plan_resp.status_code, 200)
        conv = AgentConversation.objects.filter(user=self.user).first()
        plan_json = plan_resp.context['plan_json']

        exec_resp = self.client.post(
            reverse('agent:execute'),
            {
                'plan_data': plan_json,
                'conversation_id': str(conv.id),
            },
        )
        self.assertEqual(exec_resp.status_code, 302)
        conv.refresh_from_db()
        self.assertEqual(conv.status, 'executed')
        self.assertIsNotNone(conv.project)
        self.assertTrue(mock_delay.called)

    @patch('apps.ai.views.dispatch_generation_task.delay')
    def test_one_tap_viral_effect_seeds_renders_prompt_and_queues_generation(self, mock_delay):
        effects = ViralEffectTemplate.ensure_seeded()
        self.assertGreaterEqual(effects.count(), 6)

        resp = self.client.post(
            reverse('agent:apply_effect', kwargs={'slug': 'liquid-gold-metamorphosis'}),
            {'subject': 'a vintage mechanical chronograph'},
        )
        self.assertEqual(resp.status_code, 302)
        gen = Generation.objects.filter(user=self.user).first()
        self.assertIsNotNone(gen)
        self.assertIn('a vintage mechanical chronograph', gen.prompt)
        self.assertIn('molten 24k liquid gold', gen.prompt)
        self.assertEqual(gen.provider_response.get('viral_effect'), 'liquid-gold-metamorphosis')
        self.assertTrue(mock_delay.called)

    @patch('apps.ai.views.dispatch_generation_task.delay')
    def test_load_conversation_and_inline_scene_edits_before_execution(self, mock_delay):
        plan_resp = self.client.post(
            reverse('agent:plan'),
            {
                'prompt': 'A futuristic solar airship expedition over emerald canyons',
                'aspect_ratio': '16:9',
                'skill_preset': 'anime_episodic',
            },
        )
        self.assertEqual(plan_resp.status_code, 200)
        conv = AgentConversation.objects.filter(user=self.user).first()
        self.assertIsNotNone(conv)

        # Reload saved conversation plan card via GET /agent/conversations/<id>/
        reload_resp = self.client.get(reverse('agent:conversation_detail', kwargs={'conversation_id': conv.id}))
        self.assertEqual(reload_resp.status_code, 200)

        # Modify Scene 1 title, prompt, and duration inline before executing
        plan_dict = json.loads(reload_resp.context['plan_json'])
        plan_dict['project_title'] = 'Director Cut Solar Expedition'
        plan_dict['scenes'][0]['title'] = 'Custom Opening Aerial Shot'
        plan_dict['scenes'][0]['prompt'] = 'Custom edited prompt: Golden airship breaking through storm clouds'
        plan_dict['scenes'][0]['duration'] = 8

        exec_resp = self.client.post(
            reverse('agent:execute'),
            {
                'plan_data': json.dumps(plan_dict),
                'conversation_id': str(conv.id),
            },
        )
        self.assertEqual(exec_resp.status_code, 302)
        conv.refresh_from_db()
        self.assertEqual(conv.project.name, 'Director Cut Solar Expedition')
        first_scene = conv.project.scenes.order_by('order').first()
        self.assertEqual(first_scene.title, 'Custom Opening Aerial Shot')
        self.assertEqual(first_scene.prompt, 'Custom edited prompt: Golden airship breaking through storm clouds')
        self.assertEqual(first_scene.duration, 8)
