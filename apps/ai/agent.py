import logging
import json
import httpx
from django.conf import settings
from apps.ai.schemas import StoryboardPlan, StoryboardScenePlan, CharacterCastMember
from apps.ai.safety import AgentSafetyValidator

logger = logging.getLogger(__name__)

class SuperAgent:
    """Orchestrates natural language user ideas into structured, executable multi-scene storyboards."""

    @classmethod
    def decompose_idea(cls, prompt: str, target_aspect_ratio: str = "16:9", character: object = None) -> StoryboardPlan:
        """
        Decomposes high-level user brief into a structured multi-scene storyboard with character cast.
        """
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '') or getattr(settings, 'GOOGLE_AI_API_KEY', '')
        
        if gemini_key and getattr(settings, 'AGENT_LLM_PROVIDER', 'mock') != 'mock':
            try:
                return cls._call_llm_decomposer(prompt, target_aspect_ratio, gemini_key, character=character)
            except Exception as e:
                logger.warning(f"LLM decomposition failed ({e}), falling back to intelligent rule-based planner.")

        return cls._rule_based_decomposer(prompt, target_aspect_ratio, character=character)

    @classmethod
    def _call_llm_decomposer(cls, user_prompt: str, aspect_ratio: str, api_key: str, character: object = None) -> StoryboardPlan:
        """Calls Google Gemini LLM with structured output schema including characters."""
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        char_instruction = ""
        if character:
            char_instruction = (
                f" The lead character is named '{character.name}'. "
                f"Appearance: {getattr(character, 'appearance_description', '')}. "
                f"Wardrobe: {getattr(character, 'clothing_description', '')}. Maintain this character's identity in all scenes."
            )

        system_instruction = (
            "You are CleaverLoop Super Agent, a world-class cinematic creative director. Decompose the user's idea "
            "into a 3 to 5 scene video storyboard with consistent characters and camera direction."
            f"{char_instruction} "
            "Output strictly valid JSON matching this schema: "
            '{"project_title": "...", "project_description": "...", "aspect_ratio": "...", '
            '"characters": [{"name": "...", "role": "Lead Protagonist", "description": "...", "appearance_cue": "...", "avatar_icon": "👤"}], '
            '"scenes": [{"order": 1, "title": "...", "prompt": "...", "duration": 5, "camera_direction": "...", "visual_style": "...", "dialogue": "...", "character_name": "...", "character_action": "..."}]}'
        )
        payload = {
            "contents": [{"parts": [{"text": f"User Idea: {user_prompt}\nTarget Aspect Ratio: {aspect_ratio}"}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }
        with httpx.Client(timeout=25.0) as client:
            resp = client.post(endpoint, json=payload)
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text.startswith("```json"):
                    text = text[7:]
                elif text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                data = json.loads(text)
                plan = StoryboardPlan(**data)
                if character:
                    plan.selected_character_id = str(getattr(character, 'id', ''))
                # Compute duration and credits dynamically from models
                total_sec = sum(s.duration for s in plan.scenes)
                plan.estimated_total_duration = total_sec
                plan.estimated_total_credits = cls._compute_plan_credits(plan.scenes)
                return plan
            raise RuntimeError(f"Gemini error: {resp.text[:200]}")

    @classmethod
    def _rule_based_decomposer(cls, prompt: str, aspect_ratio: str, character: object = None) -> StoryboardPlan:
        """High-quality deterministic decomposition with cast consistency."""
        title = prompt.strip().capitalize()
        if len(title) > 60:
            title = title[:57] + "..."

        # 1. Determine Cast / Characters
        characters = []
        if character:
            char_name = character.name
            char_desc = getattr(character, 'description', '') or f"Consistent identity across all storyboard scenes."
            char_cue = getattr(character, 'appearance_description', '')
            if getattr(character, 'clothing_description', ''):
                char_cue += f" Wearing: {character.clothing_description}"
            characters.append(
                CharacterCastMember(
                    name=char_name,
                    role="Lead Protagonist",
                    description=char_desc,
                    appearance_cue=char_cue or "Fixed visual likeness with persistent styling.",
                    avatar_icon="🎭"
                )
            )
            selected_char_id = str(getattr(character, 'id', ''))
        else:
            selected_char_id = None
            prompt_lower = prompt.lower()
            if "cyberpunk" in prompt_lower or "tokyo" in prompt_lower or "neon" in prompt_lower:
                char_name = "Kaelen Vance"
                characters.append(
                    CharacterCastMember(
                        name=char_name,
                        role="Cybernetic Infiltrator",
                        description="Augmented street operative in neo-futuristic metropolis.",
                        appearance_cue="Cybernetic left optical eye, glowing amber neural interface, matte carbon fiber trenchcoat.",
                        avatar_icon="⚡"
                    )
                )
            elif "claymation" in prompt_lower or "detective" in prompt_lower:
                char_name = "Barnaby Vance"
                characters.append(
                    CharacterCastMember(
                        name=char_name,
                        role="Hardboiled Investigator",
                        description="Tactile claymation stop-motion detective character.",
                        appearance_cue="Textured clay brown fedora, trench coat, expressive handcrafted stop-motion facial gestures.",
                        avatar_icon="🔍"
                    )
                )
            elif "cartoon" in prompt_lower or "1930" in prompt_lower or "baking" in prompt_lower:
                char_name = "Barnaby Baker"
                characters.append(
                    CharacterCastMember(
                        name=char_name,
                        role="Cheerful Vintage Baker",
                        description="1930s classic rubber-hose monochrome cartoon character.",
                        appearance_cue="Pie-cut eyes, oversized cartoon chef hat, white gloves, rubbery elastic limbs.",
                        avatar_icon="🎩"
                    )
                )
            elif "dance" in prompt_lower or "viral" in prompt_lower or "reel" in prompt_lower:
                char_name = "Maya Lin"
                characters.append(
                    CharacterCastMember(
                        name=char_name,
                        role="Lead Urban Dancer",
                        description="Dynamic performer with athletic streetwear aesthetic.",
                        appearance_cue="Iridescent holographic windbreaker, neon sneakers, striking motion-blur hair.",
                        avatar_icon="✨"
                    )
                )
            else:
                char_name = "Alex Mercer"
                characters.append(
                    CharacterCastMember(
                        name=char_name,
                        role="Central Protagonist",
                        description="Main character driving the visual narrative.",
                        appearance_cue="Modern sleek aesthetic, sharp cinematic lighting, consistent facial structure.",
                        avatar_icon="👤"
                    )
                )

        # Character prompt cue for scene prompts
        char_ref_text = f"Featuring {char_name} ({characters[0].appearance_cue})."

        scenes = [
            StoryboardScenePlan(
                order=1,
                title="Scene 1: The Hook & Character Intro",
                prompt=f"Cinematic opening hook for {prompt}. {char_ref_text} Atmospheric lighting, establishing wide shot, high detail.",
                duration=5,
                camera_direction="Slow push in, wide angle",
                visual_style="Cinematic 35mm film, moody volumetric lighting",
                dialogue="Every journey begins with a single moment...",
                character_name=char_name,
                character_action="Enters the environment and surveys the surroundings with focused anticipation.",
                model_preference="automatic"
            ),
            StoryboardScenePlan(
                order=2,
                title="Scene 2: Core Action & Dynamic Motion",
                prompt=f"Dynamic central action highlighting {prompt}. {char_ref_text} Vibrant colors, crisp focus, smooth motion.",
                duration=5,
                camera_direction="Tracking lateral pan, close-up",
                visual_style="Clean hyperrealistic modern commercial aesthetic",
                dialogue="Powered by advanced intelligence.",
                character_name=char_name,
                character_action="Engages in decisive hero action with dynamic energy and seamless movement.",
                model_preference="automatic"
            ),
            StoryboardScenePlan(
                order=3,
                title="Scene 3: Climax & Resolution",
                prompt=f"Impactful resolution and final hero shot representing {prompt}. {char_ref_text} Inspiring composition, premium brand feel.",
                duration=5,
                camera_direction="Drone aerial pull-back, elegant crane ascent",
                visual_style="Golden hour warm tones, clean typography space",
                dialogue="Experience the future today.",
                character_name=char_name,
                character_action="Stands triumphant in a cinematic hero pose against the horizon.",
                model_preference="automatic"
            ),
        ]

        total_sec = sum(s.duration for s in scenes)
        total_credits = cls._compute_plan_credits(scenes)

        return StoryboardPlan(
            project_title=f"AI Story: {title}",
            project_description=prompt,
            aspect_ratio=aspect_ratio,
            characters=characters,
            selected_character_id=selected_char_id,
            scenes=scenes,
            estimated_total_duration=total_sec,
            estimated_total_credits=total_credits
        )

    @classmethod
    def _compute_plan_credits(cls, scenes) -> int:
        """Calculate estimated credits across all scenes using active catalog rates."""
        from apps.providers.router import ModelRouter
        total = 0
        for s in scenes:
            try:
                m = ModelRouter.select_model(modality='video', user_preference=getattr(s, 'model_preference', 'automatic') or 'automatic', duration=s.duration)
                total += m.calculate_credit_cost(s.duration)
            except Exception:
                rate = getattr(settings, 'CREDIT_COST_VIDEO_PER_SEC', 50)
                total += 50 + (s.duration * rate)
        return total
