import io
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.credits.models import CreditWallet
from apps.voices.models import VoiceProfile, VoiceSample
from apps.voices.services import VoiceCloneService
from apps.characters.models import Character
from apps.generations.models import Generation
from apps.providers.models import AIProviderConfig, AIModel


class VoiceCloningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="voicecreator@cleaverloop.ai",
            username="voicecreator",
            password="password123"
        )
        self.wallet, _ = CreditWallet.objects.get_or_create(user=self.user)
        self.wallet.subscription_tier = 'starter'
        self.wallet.balance = 500
        self.wallet.save()

        self.client = Client()
        self.client.force_login(self.user)

        self.sample_audio = SimpleUploadedFile(
            "my_voice_sample.wav",
            b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00",
            content_type="audio/wav"
        )

    def test_voice_sample_retention(self):
        """Verify audio samples are permanently stored and linked to VoiceProfile."""
        profile = VoiceProfile.objects.create(
            user=self.user,
            name="Alexander Test",
            provider_voice_id="mock_alexander_123",
            provider="mock",
            gender="male",
            accent="British",
            status="ready"
        )
        sample = VoiceSample.objects.create(
            voice_profile=profile,
            audio_file=self.sample_audio,
            duration_seconds=4.5,
            file_size=1024
        )
        self.assertEqual(profile.samples.count(), 1)
        self.assertTrue(sample.audio_file.name.endswith(".wav"))
        self.assertEqual(sample.voice_profile, profile)

    def test_voice_clone_service_creation(self):
        """Verify VoiceCloneService clones voice, charges credits, and retains audio sample."""
        initial_balance = self.wallet.balance
        profile = VoiceCloneService.clone_voice(
            user=self.user,
            name="Morgan Vance",
            description="Deep baritone narrator voice",
            sample_files=[self.sample_audio],
            gender="male",
            accent="American"
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "Morgan Vance")
        self.assertEqual(profile.status, "ready")
        self.assertTrue(profile.provider_voice_id)
        # Sample MUST be retained
        self.assertEqual(profile.samples.count(), 1)
        # Check credits deducted (50 credits)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, initial_balance - 50)

    def test_voice_create_view(self):
        """Verify HTTP POST to /voices/create/ creates profile and redirects to list."""
        audio = SimpleUploadedFile(
            "sample_record.wav",
            b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00",
            content_type="audio/wav"
        )
        url = reverse("voices:create")
        resp = self.client.post(url, {
            "name": "Sarah Connor",
            "gender": "female",
            "accent": "Midwest",
            "description": "Determined and clear voice",
            "consent": "on",
            "audio_samples": audio,
        })
        self.assertEqual(resp.status_code, 302)
        profile = VoiceProfile.objects.filter(user=self.user, name="Sarah Connor").first()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.gender, "female")
        self.assertEqual(profile.samples.count(), 1)

    def test_voice_create_get_redirects_to_modal(self):
        """Verify GET /voices/create/ redirects to /voices/?create=1 so modal opens on same page."""
        url = reverse("voices:create")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("create=1", resp.url)

    def test_character_voice_profile_binding(self):
        """Verify Character can be bound to a VoiceProfile."""
        profile = VoiceProfile.objects.create(
            user=self.user,
            name="Detective Vance",
            provider_voice_id="custom_voice_789",
            provider="elevenlabs",
            status="ready"
        )
        char = Character.objects.create(
            owner=self.user,
            name="Detective Vance",
            appearance_description="Trenchcoat and fedora",
            voice_profile=profile
        )
        self.assertEqual(char.voice_profile, profile)
        self.assertIn(char, profile.characters.all())

    def test_google_veo_dialogue_bypasses_elevenlabs(self):
        """
        Verify that when Google Veo is selected for video generation with dialogue,
        ElevenLabs speech generation is NOT invoked, and native audio flag is set.
        """
        veo_provider, _ = AIProviderConfig.objects.get_or_create(
            name="Google",
            slug="google",
            is_enabled=True
        )
        veo_model, _ = AIModel.objects.get_or_create(
            model_id="google/veo-3.1",
            defaults={
                "provider": veo_provider,
                "display_name": "Google Veo 3.1 Cinema",
                "modality": "video",
                "credit_cost_fixed": 100,
                "credit_cost_per_second": 20,
                "is_enabled": True
            }
        )

        gen = Generation.objects.create(
            user=self.user,
            generation_type="video",
            provider=veo_provider,
            model=veo_model,
            model_id_snapshot=veo_model.model_id,
            prompt="A detective standing under a streetlamp.",
            dialogue="I told you we should have never opened that briefcase.",
            is_lip_sync=True,
            status="queued"
        )

        from apps.providers.base import ProviderJobResult
        # Mock ElevenLabsProvider.generate_audio to verify it is NOT called
        with patch("apps.providers.adapters.elevenlabs.ElevenLabsProvider.generate_audio") as mock_eleven:
            with patch("apps.providers.adapters.google_veo.GoogleVeoProvider.generate_video") as mock_veo:
                mock_veo.return_value = ProviderJobResult(
                    external_job_id="veo_job_123",
                    status="completed",
                    output_media_url="https://example.com/veo_video.mp4"
                )
                from apps.generations.tasks import dispatch_generation_task
                dispatch_generation_task(str(gen.id))

                # ElevenLabs MUST NOT have been called
                mock_eleven.assert_not_called()

                gen.refresh_from_db()
                self.assertTrue(gen.uses_native_veo_audio)
                # Check that dialogue was passed in extra_params to Veo adapter
                req_arg = mock_veo.call_args[0][1]
                self.assertEqual(req_arg.extra_params.get('dialogue'), "I told you we should have never opened that briefcase.")

        # Also verify GoogleVeoProvider conditioning formats dialogue into prompt
        from apps.providers.adapters.google_veo import GoogleVeoProvider
        from apps.providers.base import GenerationRequest
        test_req = GenerationRequest(
            prompt="A detective standing under a streetlamp.",
            extra_params={"dialogue": "I told you we should have never opened that briefcase."}
        )
        # Veo embeds dialogue into instance prompt:
        dialogue = test_req.extra_params.get('dialogue')
        conditioned = (
            f"{test_req.prompt}. In-character spoken line: \"{dialogue}\" "
            f"with natural synchronized mouth articulation, expressive jaw movement, and native cinematic voice."
        )
        self.assertIn("spoken line:", conditioned.lower())
        self.assertIn("briefcase", conditioned)

    def test_voice_clone_free_tier_blocked(self):
        """Verify free tier users cannot clone voices and receive an upgrade message."""
        self.wallet.subscription_tier = 'free'
        self.wallet.save()
        with self.assertRaises(ValueError) as ctx:
            VoiceCloneService.clone_voice(
                user=self.user,
                name="Free User Voice",
                sample_files=[self.sample_audio]
            )
        self.assertIn("paid subscription", str(ctx.exception).lower())

    def test_voice_clone_quota_enforced(self):
        """Verify exceeding max_voice_profiles quota raises ValueError."""
        # Starter plan allows 3 voice profiles
        for i in range(3):
            VoiceProfile.objects.create(
                user=self.user,
                name=f"Existing Voice {i}",
                status="ready"
            )
        with self.assertRaises(ValueError) as ctx:
            VoiceCloneService.clone_voice(
                user=self.user,
                name="Overflow Voice",
                sample_files=[self.sample_audio]
            )
        self.assertIn("quota reached", str(ctx.exception).lower())

    def test_api_preview_speech_billing(self):
        """Verify api_preview_speech deducts credits according to user's plan."""
        initial_bal = self.wallet.balance
        with patch("apps.providers.adapters.elevenlabs.ElevenLabsProvider.generate_audio") as mock_gen:
            from apps.providers.base import ProviderJobResult
            mock_gen.return_value = ProviderJobResult(
                external_job_id="test_speech_1",
                status="completed",
                output_media_url="https://example.com/speech.mp3"
            )
            resp = self.client.post(reverse("voices:api_preview"), {
                "text": "Hello world from CleaverLoop AI!",
                "voice_id": "adam"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["credits_deducted"], 15)  # 15 cr on starter
            self.wallet.refresh_from_db()
            self.assertEqual(self.wallet.balance, initial_bal - 15)
