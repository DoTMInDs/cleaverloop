import logging
import json
import httpx
from django.conf import settings
from apps.ai.schemas import StoryboardPlan, StoryboardScenePlan
from apps.ai.safety import AgentSafetyValidator

logger = logging.getLogger(__name__)

class SuperAgent:
    """Orchestrates natural language user ideas into structured, executable multi-scene storyboards."""

    @classmethod
    def decompose_idea(cls, prompt: str, target_aspect_ratio: str = "16:9") -> StoryboardPlan:
        """
        Decomposes high-level user brief into a structured multi-scene storyboard.
        """
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '') or getattr(settings, 'GOOGLE_AI_API_KEY', '')
        
        if gemini_key and getattr(settings, 'AGENT_LLM_PROVIDER', 'mock') != 'mock':
            try:
                return cls._call_llm_decomposer(prompt, target_aspect_ratio, gemini_key)
            except Exception as e:
                logger.warning(f"LLM decomposition failed ({e}), falling back to intelligent rule-based planner.")

        return cls._rule_based_decomposer(prompt, target_aspect_ratio)

    @classmethod
    def _call_llm_decomposer(cls, user_prompt: str, aspect_ratio: str, api_key: str) -> StoryboardPlan:
        """Calls Google Gemini LLM with structured output schema."""
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        system_instruction = (
            "You are CleverLoop Super Agent, a world-class creative director. Decompose the user's idea "
            "into a 3 to 5 scene video storyboard. Output strictly valid JSON matching this schema: "
            '{"project_title": "...", "project_description": "...", "aspect_ratio": "...", '
            '"scenes": [{"order": 1, "title": "...", "prompt": "...", "duration": 5, "camera_direction": "...", "visual_style": "..."}]}'
        )
        payload = {
            "contents": [{"parts": [{"text": f"User Idea: {user_prompt}\nTarget Aspect Ratio: {aspect_ratio}"}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }
        with httpx.Client(timeout=25.0) as client:
            resp = client.post(endpoint, json=payload)
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(text)
                plan = StoryboardPlan(**data)
                # Compute duration and credits
                total_sec = sum(s.duration for s in plan.scenes)
                plan.estimated_total_duration = total_sec
                plan.estimated_total_credits = len(plan.scenes) * 50 + (total_sec * 50)
                return plan
            raise RuntimeError(f"Gemini error: {resp.text[:200]}")

    @classmethod
    def _rule_based_decomposer(cls, prompt: str, aspect_ratio: str) -> StoryboardPlan:
        """High-quality deterministic decomposition for offline or mock mode."""
        title = prompt.strip().capitalize()
        if len(title) > 60:
            title = title[:57] + "..."

        scenes = [
            StoryboardScenePlan(
                order=1,
                title="Scene 1: The Hook & Opening",
                prompt=f"Cinematic opening hook for {prompt}. Atmospheric lighting, establishing wide shot, high detail.",
                duration=5,
                camera_direction="Slow push in, wide angle",
                visual_style="Cinematic 35mm film, moody volumetric lighting",
                dialogue="Every journey begins with a single moment...",
                model_preference="automatic"
            ),
            StoryboardScenePlan(
                order=2,
                title="Scene 2: Core Concept & Detail",
                prompt=f"Dynamic central action highlighting {prompt}. Vibrant colors, crisp focus, smooth motion.",
                duration=5,
                camera_direction="Tracking lateral pan, close-up",
                visual_style="Clean hyperrealistic modern commercial aesthetic",
                dialogue="Powered by advanced intelligence.",
                model_preference="automatic"
            ),
            StoryboardScenePlan(
                order=3,
                title="Scene 3: Climax & Call to Action",
                prompt=f"Impactful resolution and final hero shot representing {prompt}. Inspiring composition, premium brand feel.",
                duration=5,
                camera_direction="Drone aerial pull-back, elegant crane ascent",
                visual_style="Golden hour warm tones, clean typography space",
                dialogue="Experience the future today.",
                model_preference="automatic"
            ),
        ]

        total_sec = sum(s.duration for s in scenes)
        total_credits = len(scenes) * 50 + (total_sec * 50)

        return StoryboardPlan(
            project_title=f"AI Story: {title}",
            project_description=prompt,
            aspect_ratio=aspect_ratio,
            scenes=scenes,
            estimated_total_duration=total_sec,
            estimated_total_credits=total_credits
        )
