import os
import io
import uuid
import json
import logging
import httpx
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from apps.characters.schemas import CharacterDNASchema

logger = logging.getLogger(__name__)

class CharacterGeneratorService:
    """Intelligent AI Character Generation Engine decomposing user briefs into rich character DNA and portraits."""

    STYLE_PRESETS = {
        'cinematic': 'Cinematic 8K, photorealistic, 35mm film photography, dramatic lighting, sharp focus',
        'anime': 'Modern anime digital illustration, Makoto Shinkai aesthetic, vibrant colors, detailed eyes, expressive lighting',
        'cyberpunk': 'Neo-Tokyo cyberpunk, volumetric neon fog, glowing holographic interface reflections, carbon fiber textures',
        'fantasy': 'Dark high fantasy, painterly digital concept art, intricate armor detailing, ethereal magical glow',
        'pixar_3d': 'Stylized 3D cinematic animation character, Octane render, charming expressive facial features, soft studio lighting',
        'vintage_cartoon': '1930s classic rubber-hose monochrome animation, pie-cut eyes, bouncy whimsical aesthetic'
    }

    @classmethod
    def synthesize_character(cls, brief: str, style_preset: str = "cinematic") -> CharacterDNASchema:
        """Synthesizes complete Character DNA from a natural language brief and generates an avatar portrait."""
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '') or getattr(settings, 'GOOGLE_AI_API_KEY', '')
        
        dna = None
        if gemini_key and getattr(settings, 'AGENT_LLM_PROVIDER', 'mock') != 'mock':
            try:
                dna = cls._call_gemini_dna(brief, style_preset, gemini_key)
            except Exception as e:
                logger.warning(f"Gemini character synthesis failed ({e}), falling back to intelligent rule engine.")

        if not dna:
            dna = cls._rule_based_dna(brief, style_preset)

        # Generate character portrait avatar
        avatar_url = cls.generate_avatar_portrait(dna, style_preset)
        dna.avatar_url = avatar_url

        return dna

    @classmethod
    def _call_gemini_dna(cls, brief: str, style_preset: str, api_key: str) -> CharacterDNASchema:
        """Invokes Gemini LLM for structured character DNA generation."""
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        style_desc = cls.STYLE_PRESETS.get(style_preset, cls.STYLE_PRESETS['cinematic'])

        system_prompt = (
            "You are CleaverLoop AI Character Architect. Given a user concept brief, create a world-class, consistent AI Character. "
            "Output strictly valid JSON with this exact schema: "
            '{"name": "...", "tagline": "...", "description": "...", "appearance_description": "...", '
            '"clothing_description": "...", "personality": "...", "portrait_prompt": "..."}\n'
            f"Visual Style Direction: {style_desc}. Ensure portrait_prompt is an optimized high-detail prompt for an 8k portrait."
        )

        payload = {
            "contents": [{"parts": [{"text": f"Character Brief: {brief}\nStyle: {style_preset}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
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
                return CharacterDNASchema(**data)
            raise RuntimeError(f"Gemini API returned status {resp.status_code}")

    @classmethod
    def _rule_based_dna(cls, brief: str, style_preset: str) -> CharacterDNASchema:
        """High-fidelity contextual character generation engine for offline/fallback mode."""
        brief_lower = brief.lower()
        style_desc = cls.STYLE_PRESETS.get(style_preset, cls.STYLE_PRESETS['cinematic'])

        # Contextual Archetype detection
        if any(w in brief_lower for w in ['cyber', 'neon', 'tokyo', 'hacker', 'samurai', 'blade', 'mech']):
            name = "Kaelen Kurogane"
            tagline = "Cybernetic Infiltrator & Netrunner"
            desc = f"An augmented specialist navigating high-tech urban sprawls. Inspired by: '{brief}'."
            appearance = "27-year-old operative with angular jawline, striking luminescent cyan cybernetic left iris, sleek raven-black undercut hair with subtle fiber-optic strands, and micro-circuitry along temple."
            clothing = "Matte-black ballistic leather bomber jacket with glowing amber internal lining, fitted tactical carbon-weave pants, magnetic collar harness."
            personality = "Hyper-focused, sharp analytical gaze, calm under extreme pressure, subtle confident smirk."
        elif any(w in brief_lower for w in ['detective', 'noir', 'mystery', 'investigator', 'sherlock', 'fedora']):
            name = "Barnaby Cross"
            tagline = "Hardboiled Noir Investigator"
            desc = f"A relentless investigator who uncovers hidden truths in shadowy alleys. Inspired by: '{brief}'."
            appearance = "42-year-old detective, rugged five-o'clock shadow, deep-set piercing hazel eyes, dark wavy hair with silver temples, expressive furrowed brow."
            clothing = "Heavy charcoal wool trenchcoat, loosened vintage silk tie, brass-buckled holster, weathered charcoal fedora."
            personality = "Perceptive, cynical yet deeply empathetic, measured baritone cadence, observant steady gaze."
        elif any(w in brief_lower for w in ['space', 'star', 'pilot', 'commander', 'cosmic', 'galaxy', 'astro']):
            name = "Captain Lyra Vance"
            tagline = "Deep Space Explorer & Fleet Commander"
            desc = f"A visionary starship commander leading deep space expeditions. Inspired by: '{brief}'."
            appearance = "34-year-old commander, radiant olive skin tone, steel-blue eyes with golden flecks, cropped ash-blonde hair, subtle tactical scar over right brow."
            clothing = "Ceramic composite naval commander suit in deep obsidian navy with burnished gold rank seals and magnetic interface cuffs."
            personality = "Authoritative, inspiring, decisive in crisis, unyielding visionary determination."
        elif any(w in brief_lower for w in ['dance', 'music', 'dj', 'street', 'urban', 'pop', 'singer', 'viral']):
            name = "Maya Lin"
            tagline = "Vanguard Urban Performer"
            desc = f"A powerhouse creator and dynamic performer bringing electrifying energy. Inspired by: '{brief}'."
            appearance = "22-year-old urban dancer, glowing warm skin tone, sparkling dark brown eyes, high ponytail with electric purple highlights, athletic sculpted build."
            clothing = "Iridescent holographic windbreaker over black cropped athletic top, reflective cargo joggers, glowing sneakers."
            personality = "Magnetic, electric charisma, infectious smile, limitless creative drive."
        elif any(w in brief_lower for w in ['fantasy', 'wizard', 'witch', 'mage', 'elf', 'knight', 'magic', 'dragon']):
            name = "Elowen Stormchaser"
            tagline = "Ethereal Spellblade Weaver"
            desc = f"A master of arcane martial arts blending ancient magic with bladed combat. Inspired by: '{brief}'."
            appearance = "Ageless elven aesthetic, luminous silver hair falling in braided waves, glowing violet irises, sculpted graceful facial features, faint arcane runes along neck."
            clothing = "Midnight velvet and embossed mithril tunic, gilded pauldrons, flowing raven cloak lined with starlight runes."
            personality = "Mysterious, ancient wisdom, poised, intense captivating presence."
        elif any(w in brief_lower for w in ['cartoon', '1930', 'rubber', 'baking', 'slapstick', 'bouncy']):
            name = "Barnaby Baker"
            tagline = "Vintage Rubber-Hose Cartoon Hero"
            desc = f"A cheerful vintage animated baker with elastic slapstick limbs. Inspired by: '{brief}'."
            appearance = "Monochrome 1930s cartoon character, pie-cut expressive eyes, rubbery bendable limbs, cheerful round facial contours, oversized chef toque."
            clothing = "Pinstripe cartoon apron, oversized four-finger white gloves, bouncy oversized clown shoes."
            personality = "Whimsical, perpetually cheerful, bouncy optimism, slapstick mischief."
        else:
            # General custom synthesis
            name = brief.strip().title() if len(brief.strip().split()) <= 2 else "Alex Mercer"
            tagline = "Visionary Central Protagonist"
            desc = f"A distinctive AI character tailored to your creative vision: '{brief}'."
            appearance = f"Distinctive character featuring {brief}. Sharp facial bone structure, expressive eyes, modern tailored hairstyle, warm cinematic illumination."
            clothing = "Modern sleek designer outfit with clean lines, high-contrast textures, and tailored accessories."
            personality = "Confident, charismatic, observant, captivating screen presence."

        portrait_prompt = (
            f"Close-up masterpiece character portrait of {name} ({tagline}). "
            f"{appearance}. Wearing: {clothing}. {personality}. "
            f"{style_desc}, 8k resolution, photorealistic, intricate facial details, cinematic portrait lighting."
        )

        return CharacterDNASchema(
            name=name,
            tagline=tagline,
            description=desc,
            appearance_description=appearance,
            clothing_description=clothing,
            personality=personality,
            portrait_prompt=portrait_prompt
        )

    @classmethod
    def generate_avatar_portrait(cls, dna: CharacterDNASchema, style_preset: str = "cinematic") -> str:
        """Generates a high-definition synthetic character avatar and saves to media storage."""
        width, height = 512, 512
        image = Image.new('RGB', (width, height), color=(14, 16, 20))
        draw = ImageDraw.Draw(image)

        # Draw deep luxury obsidian background with amber/orange radiant aura
        for r in range(240, 40, -10):
            alpha = int((240 - r) * 0.4)
            color = (
                min(255, 20 + int(alpha * 1.8)),
                min(255, 15 + int(alpha * 0.9)),
                min(255, 10 + int(alpha * 0.3))
            )
            draw.ellipse([256 - r, 230 - r, 256 + r, 230 + r], fill=color)

        # Draw background grid mesh
        for x in range(0, width, 32):
            draw.line([(x, 0), (x, height)], fill=(25, 28, 34), width=1)
        for y in range(0, height, 32):
            draw.line([(0, y), (width, y)], fill=(25, 28, 34), width=1)

        # Draw avatar halo ring
        draw.ellipse([128, 90, 384, 346], outline=(249, 115, 22), width=3)
        draw.ellipse([136, 98, 376, 338], outline=(251, 146, 60), width=1)

        # Draw avatar head/shoulders icon silhouette
        draw.ellipse([206, 138, 306, 238], fill=(35, 40, 50), outline=(249, 115, 22), width=2)
        draw.polygon([(166, 330), (216, 258), (296, 258), (346, 330)], fill=(30, 34, 42), outline=(249, 115, 22))

        # Draw Character Monogram inside silhouette
        initials = "".join([part[0].upper() for part in dna.name.split()[:2]]) or "AI"
        try:
            font = ImageFont.truetype("arial.ttf", 36)
            font_sm = ImageFont.truetype("arial.ttf", 16)
        except Exception:
            font = ImageFont.load_default()
            font_sm = font

        draw.text((256, 188), initials, fill=(255, 255, 255), anchor="mm", font=font)

        # Draw Character Name Banner at Bottom
        draw.rectangle([0, 420, width, height], fill=(10, 11, 14))
        draw.line([(0, 420), (width, 420)], fill=(249, 115, 22), width=2)
        draw.text((256, 445), dna.name.upper(), fill=(255, 255, 255), anchor="mm", font=font_sm)
        draw.text((256, 475), f"🔒 {dna.tagline} • ZERO DRIFT", fill=(249, 115, 22), anchor="mm", font=font_sm)

        # Save to media storage
        buffer = io.BytesIO()
        image.save(buffer, format='PNG', optimize=True)
        filename = f"characters/avatars/ai_{uuid.uuid4().hex[:10]}.png"
        saved_path = default_storage.save(filename, ContentFile(buffer.getvalue()))
        return default_storage.url(saved_path)
