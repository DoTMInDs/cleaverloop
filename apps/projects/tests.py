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

    def test_user_can_add_and_delete_scene(self):
        """Verify project owner can add and delete scenes."""
        self.client.login(email="alice@cleaverloop.ai", password="password123")
        add_url = reverse('projects:add_scene', kwargs={'project_id': self.project_a.pk})
        resp = self.client.post(add_url, {
            'title': 'Scene 2: Climax',
            'prompt': 'A hero standing tall',
            'duration': 6
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.project_a.scenes.count(), 2)

        new_scene = self.project_a.scenes.order_by('-order').first()
        self.assertEqual(new_scene.order, 2)
        self.assertEqual(new_scene.duration, 6)

        # Delete scene
        del_url = reverse('projects:delete_scene', kwargs={'scene_id': new_scene.id})
        del_resp = self.client.post(del_url)
        self.assertEqual(del_resp.status_code, 302)
        self.assertEqual(self.project_a.scenes.count(), 1)

    def test_user_cannot_delete_other_users_scene(self):
        """Verify User B cannot delete User A's scene."""
        self.client.login(email="bob@cleaverloop.ai", password="password123")
        del_url = reverse('projects:delete_scene', kwargs={'scene_id': self.scene_a.id})
        del_resp = self.client.post(del_url)
        self.assertEqual(del_resp.status_code, 404)
        self.assertTrue(Scene.objects.filter(id=self.scene_a.id).exists())

    def test_job_status_api_requires_login_and_owner(self):
        """Verify editor job_status_api requires authentication and scopes to owner."""
        from apps.editor.models import AssemblyJob
        job = AssemblyJob.objects.create(
            project=self.project_a,
            user=self.user_a,
            status='rendering'
        )

        job_url = reverse('editor:job_status', kwargs={'job_id': job.id})

        # Anonymous request redirects to login
        anon_client = self.client_class()
        anon_resp = anon_client.get(job_url)
        self.assertEqual(anon_resp.status_code, 302)

        # Other user receives 404 (IDOR prevented)
        self.client.login(email="bob@cleaverloop.ai", password="password123")
        bob_resp = self.client.get(job_url)
        self.assertEqual(bob_resp.status_code, 404)

        # Owner receives 200
        self.client.login(email="alice@cleaverloop.ai", password="password123")
        owner_resp = self.client.get(job_url)
        self.assertEqual(owner_resp.status_code, 200)
        self.assertEqual(owner_resp.json()['status'], 'rendering')
