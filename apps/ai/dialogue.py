import logging
import json
import re
import httpx
from typing import Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

class AIDialogueDirector:
    """
    Intelligent AI Screenplay & Voice Director.
    Dynamically analyzes visual story scene prompts to deduce the character's intent,
    emotions, and realistic 1st-person spoken dialogue or inner monologue
    strictly paced to match the exact video clip duration.
    """

    @classmethod
    def deduce_dialogue(
        cls,
        prompt: str,
        character_name: str = "",
        duration: int = 5,
        style: str = "dialogue",
        character_gender: str = ""
    ) -> Dict[str, Any]:
        """
        Main entrypoint: Deduces speech and suggested voice persona using AI LLM
        with automatic fallback to advanced linguistic synthesis.
        """
        duration = max(int(duration or 5), 1)
        target_words = max(int(duration * 2.3), 6)  # ~11 words for 5s, ~23 words for 10s

        gemini_key = getattr(settings, 'GEMINI_API_KEY', '') or getattr(settings, 'GOOGLE_AI_API_KEY', '')
        openai_key = getattr(settings, 'OPENAI_API_KEY', '')

        # 1. Try Gemini LLM
        if gemini_key:
            try:
                result = cls._call_gemini_dialogue(prompt, character_name, duration, target_words, style, gemini_key)
                if result and result.get("dialogue"):
                    return result
            except Exception as exc:
                logger.warning(f"Gemini dialogue deduction failed ({exc}), trying next provider.")

        # 2. Try OpenAI LLM
        if openai_key:
            try:
                result = cls._call_openai_dialogue(prompt, character_name, duration, target_words, style, openai_key)
                if result and result.get("dialogue"):
                    return result
            except Exception as exc:
                logger.warning(f"OpenAI dialogue deduction failed ({exc}), falling back to linguistic engine.")

        # 3. Dynamic Linguistic Synthesis
        return cls._synthesize_linguistic_dialogue(prompt, character_name, duration, target_words, style, character_gender)

    @classmethod
    def _call_gemini_dialogue(
        cls,
        prompt: str,
        character_name: str,
        duration: int,
        target_words: int,
        style: str,
        api_key: str
    ) -> Optional[Dict[str, Any]]:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        system_instruction = (
            "You are an award-winning Hollywood film director and screenwriter. "
            "Your task is to analyze a visual video shot prompt and deduce what the character is doing, feeling, "
            "and aiming to accomplish, then write an authentic FIRST-PERSON spoken line or internal monologue. "
            "CRITICAL RULES:\n"
            "1. MUST be in 1st person ('I', 'my', 'we'). The character is speaking directly.\n"
            "2. NEVER describe the visual scene or act like a narrator (never say 'He is walking' or 'The scene shows').\n"
            f"3. STRICT LENGTH LIMIT: Exactly between 5 and {target_words} words so it fits a {duration}-second video clip without running over.\n"
            "4. Return STRICT valid JSON with fields: 'dialogue' (str), 'suggested_voice' ('adam'|'rachel'|'nicole'|'antoni'|'josh'|'george'|'bella'|'arnold'|'sam'), 'emotion' (str), 'intent' (str)."
        )

        user_content = (
            f"Video Scene Shot: {prompt}\n"
            f"Character Name: {character_name or 'Lead Character'}\n"
            f"Mode: {'Inner Monologue' if style == 'monologue' else ('Cinematic Sound FX / Foley Description' if style == 'foley' else 'Direct Spoken Dialogue')}\n"
            f"Target Duration: {duration} seconds (Max {target_words} spoken words)."
        )

        payload = {
            "contents": [{"parts": [{"text": user_content}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }

        with httpx.Client(timeout=12.0) as client:
            headers = {"x-goog-api-key": api_key}
            resp = client.post(endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                data = json.loads(raw_text)
                dialogue = data.get("dialogue", "").strip().strip('"').strip("'")
                words = dialogue.split()
                if len(words) > target_words + 2:
                    dialogue = " ".join(words[:target_words]) + "..."
                return {
                    "dialogue": dialogue,
                    "suggested_voice": data.get("suggested_voice", "adam"),
                    "emotion": data.get("emotion", "Focused"),
                    "word_count": len(dialogue.split()),
                    "estimated_seconds": round(len(dialogue.split()) / 2.3, 1),
                    "duration": duration,
                    "provider": "gemini"
                }
        return None

    @classmethod
    def _call_openai_dialogue(
        cls,
        prompt: str,
        character_name: str,
        duration: int,
        target_words: int,
        style: str,
        api_key: str
    ) -> Optional[Dict[str, Any]]:
        endpoint = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        system_msg = (
            f"You are a cinematic dialogue writer. Write a short 1st-person spoken line (max {target_words} words) "
            f"for a character in a {duration}-second video. Never narrate. Return JSON: {{'dialogue': '...', 'suggested_voice': 'adam', 'emotion': '...'}}"
        )

        user_msg = f"Shot: {prompt}\nCharacter: {character_name}\nMode: {style}\nDuration: {duration}s"

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7
        }

        with httpx.Client(timeout=12.0) as client:
            resp = client.post(endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()["choices"][0]["message"]["content"]
                parsed = json.loads(data)
                dialogue = parsed.get("dialogue", "").strip().strip('"')
                return {
                    "dialogue": dialogue,
                    "suggested_voice": parsed.get("suggested_voice", "adam"),
                    "emotion": parsed.get("emotion", "Determined"),
                    "word_count": len(dialogue.split()),
                    "estimated_seconds": round(len(dialogue.split()) / 2.3, 1),
                    "duration": duration,
                    "provider": "openai"
                }
        return None

    @classmethod
    def _synthesize_linguistic_dialogue(
        cls,
        prompt: str,
        character_name: str,
        duration: int,
        target_words: int,
        style: str,
        character_gender: str = ""
    ) -> Dict[str, Any]:
        """
        Advanced heuristic parser that deduces character intent from story actions,
        objects, emotional beats, and settings.
        """
        p_lower = prompt.lower()
        is_female = character_gender.lower() == 'female' or bool(re.search(r'\b(woman|girl|female|she|her|mother|sister|lady)\b', p_lower))
        suggested_voice = "rachel" if is_female else "adam"

        if style == 'foley':
            clean_scene = re.sub(r'\b(cinematic|8k|4k|photorealistic|hyper-detailed|unreal engine|35mm|tracking shot|close-up|drone shot|render|masterpiece)\b', '', prompt, flags=re.IGNORECASE).strip()
            return {
                "dialogue": f"Realistic environmental ambient foley, footsteps, atmosphere, and subtle cinematic score for: {clean_scene}",
                "suggested_voice": suggested_voice,
                "emotion": "Atmospheric",
                "word_count": 0,
                "estimated_seconds": duration,
                "duration": duration,
                "provider": "foley_synthesizer"
            }

        # 1. Deduce Scene Intent & Story Goal
        if any(k in p_lower for k in ['interview', 'cv', 'certificate', 'folder', 'suit', 'resume', 'hire', 'job']):
            emotion = "Determined & Hopeful"
            if style == 'monologue':
                line = "Everything comes down to this interview... I'm ready to make it count." if duration <= 6 else "I've prepared for this day with everything in this folder. Today, I'm going to make this interview count."
            else:
                line = "I have my certificates ready... today, I'm getting that job." if duration <= 6 else "I've organized every certificate in this folder. I'm ready to walk into this interview and show what I can do."

        elif any(k in p_lower for k in ['car', 'suv', 'luxury', 'vehicle', 'admire', 'admiration', 'dream', 'drive', 'speed']):
            emotion = "Aspirational & Ambitious"
            if style == 'monologue':
                line = "Just watch... with enough focus, that's going to be mine." if duration <= 6 else "Look at that ride. Keep grinding every day, because soon enough, you'll be behind that wheel."
            else:
                line = "One day... that is going to be me behind that wheel." if duration <= 6 else "Look at that vehicle. With the hard work I'm putting in, I know I'll be driving one soon."

        elif any(k in p_lower for k in ['walk', 'walking', 'street', 'road', 'city', 'town', 'market', 'accra', 'tro-tro', 'journey']):
            emotion = "Focused & Relentless"
            if style == 'monologue':
                line = "One step at a time... no looking back now." if duration <= 6 else "Every single step through this city brings me closer to the goal. The journey starts right here."
            else:
                line = "Stepping through this busy city... time to make things happen." if duration <= 6 else "Moving with pure focus through these streets. Today is all about progress and executing my plan."

        elif any(k in p_lower for k in ['meeting', 'office', 'tech', 'work', 'laptop', 'desk', 'presentation', 'code']):
            emotion = "Professional & Confident"
            suggested_voice = "nicole" if is_female else "josh"
            line = "Let's review the plan and build something extraordinary." if duration <= 6 else "We have the strategy in place. Now it's time to execute with precision and deliver extraordinary results."

        elif any(k in p_lower for k in ['success', 'celebrat', 'smile', 'happy', 'win', 'won', 'triumph']):
            emotion = "Joyful & Victorious"
            suggested_voice = "bella" if is_female else "sam"
            line = "We actually did it... all that effort was completely worth it!" if duration <= 6 else "Looking back at where we started, this moment feels amazing. We put in the work and achieved it."

        elif any(k in p_lower for k in ['danger', 'fight', 'run', 'escape', 'chase', 'dark', 'action', 'threat']):
            emotion = "Urgent & Intense"
            suggested_voice = "arnold" if not is_female else "nicole"
            line = "No time to hesitate... we move right now!" if duration <= 6 else "We have to stay sharp and move fast. Keep your head down and stay with me!"

        else:
            emotion = "Reflective & Direct"
            # Strip technical camera words
            cleaned = re.sub(r'\b(cinematic|8k|4k|photorealistic|hyper-detailed|unreal engine|35mm|tracking shot|close-up|drone shot|render|masterpiece|dramatic lighting|ray tracing)\b', '', prompt, flags=re.IGNORECASE)
            cleaned = re.sub(r'^(a young man|a man|a woman|a person|the character|a character)\s+', '', cleaned, flags=re.IGNORECASE).strip()
            words = cleaned.split()
            if len(words) > target_words:
                cleaned = " ".join(words[:target_words])
            line = f"Alright... time to take this step and make it happen." if not cleaned else f"Alright... time to step forward and see this through."

        # Strict length formatting
        words = line.split()
        if len(words) > target_words + 2:
            line = " ".join(words[:target_words]) + "..."

        return {
            "dialogue": line,
            "suggested_voice": suggested_voice,
            "emotion": emotion,
            "word_count": len(line.split()),
            "estimated_seconds": round(len(line.split()) / 2.3, 1),
            "duration": duration,
            "provider": "linguistic_deducer"
        }
