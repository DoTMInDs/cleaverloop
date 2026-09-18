import json
from django.test import TestCase, Client
from apps.accounts.models import User
from apps.credits.models import CreditWallet
from apps.credits.services import CreditService
from apps.ai.safety import AgentSafetyValidator, SceneLimitExceededError, BudgetExceededError
from apps.ai.schemas import StoryboardPlan, StoryboardScenePlan
from apps.providers.registry import ModelRegistry

class SuperAgentSafetyTests(TestCase):
    def setUp(self):
        ModelRegistry.seed_initial_catalog()
        self.user = User.objects.create_user(email="director@cleaverloop.ai", username="director", password="password123")
        self.wallet = CreditWallet.objects.get(user=self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def test_plan_exceeding_max_scenes_rejected(self):
        """Verify AgentSafetyValidator rejects plans with > 6 scenes."""
        scenes = [
            StoryboardScenePlan(order=i, title=f"Scene {i}", prompt=f"Action sequence {i}", duration=5)
            for i in range(1, 8)  # 7 scenes (limit is 6)
        ]
        plan = StoryboardPlan(
            project_title="Overlong Movie",
            project_description="Test description",
            aspect_ratio="16:9",
            estimated_total_credits=500,
            scenes=scenes
        )
        with self.assertRaises(SceneLimitExceededError):
            AgentSafetyValidator.validate_plan(plan, self.wallet)

    def test_plan_exceeding_budget_rejected(self):
        """Verify AgentSafetyValidator rejects plans exceeding credit cap."""
        scenes = [
            StoryboardScenePlan(order=1, title="Huge Scene", prompt="Huge sequence", duration=10)
        ]
        plan = StoryboardPlan(
            project_title="Expensive Movie",
            project_description="Test description",
            aspect_ratio="16:9",
            estimated_total_credits=3000,  # Limit is 2500
            scenes=scenes
        )
        with self.assertRaises(BudgetExceededError):
            AgentSafetyValidator.validate_plan(plan, self.wallet)

    def test_tampered_client_post_plan_rejected(self):
        """Verify execute_agent_plan_view strictly rejects tampered JSON with excessive scenes."""
        tampered_scenes = [
            {"order": i, "title": f"Scene {i}", "prompt": f"Action sequence {i}", "duration": 5}
            for i in range(1, 10)  # 9 scenes
        ]
        tampered_data = {
            "project_title": "Tampered Plan",
            "project_description": "Hacked",
            "aspect_ratio": "16:9",
            "estimated_total_credits": 200,
            "scenes": tampered_scenes
        }
        from django.urls import reverse

        resp = self.client.post(reverse('agent:execute'), {
            'plan_data': json.dumps(tampered_data)
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("exceeds the limit of 6 scenes", resp.content.decode('utf-8'))
