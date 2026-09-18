from django.test import TestCase
from django.urls import reverse
from apps.accounts.models import User
from apps.projects.models import Project, Scene

class ProjectAuthorizationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(email="alice@cleaverloop.ai", username="alice", password="password123")
        self.user_b = User.objects.create_user(email="bob@cleaverloop.ai", username="bob", password="password123")
        
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name="Alice Confidential Ad",
            aspect_ratio="16:9"
        )
        self.scene_a = Scene.objects.create(
            project=self.project_a,
            order=1,
            title="Scene 1",
            prompt="Secret commercial scene",
            duration=5
        )

    def test_user_cannot_access_other_users_project(self):
        """Verify User B receives 404 when accessing User A's project detail."""
        self.client.login(email="bob@cleaverloop.ai", password="password123")
        response = self.client.get(reverse('projects:detail', kwargs={'pk': self.project_a.pk}))
        self.assertEqual(response.status_code, 404)

    def test_user_cannot_generate_other_users_scene(self):
        """Verify User B cannot trigger generation on User A's scene."""
        self.client.login(email="bob@cleaverloop.ai", password="password123")
        response = self.client.post(reverse('projects:generate_scene', kwargs={'scene_id': self.scene_a.id}))
        self.assertEqual(response.status_code, 404)
