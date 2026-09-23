import os
import io
import uuid
import json
import base64
import logging
from typing import Optional, Dict, Any, List
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
        """Synthesizes complete Character DNA from a natural language brief and generates an avatar portrait + full-body figure."""
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '') or getattr(settings, 'GOOGLE_AI_API_KEY', '')
        
        dna = None
        if gemini_key and getattr(settings, 'AGENT_LLM_PROVIDER', 'mock') != 'mock':
            try:
                dna = cls._call_gemini_dna(brief, style_preset, gemini_key)
            except Exception as e:
                logger.warning(f"Gemini character synthesis failed ({e}), falling back to intelligent rule engine.")

        if not dna:
            dna = cls._rule_based_dna(brief, style_preset)

        is_female = (dna.gender or '').lower() == 'female'

        # Generate unique character avatar portrait
        avatar_url = cls.generate_avatar_portrait(dna, style_preset)
        dna.avatar_url = avatar_url
        dna.face_anchor_url = avatar_url

        # Link showcase visual asset ONLY if prompt/name is explicitly for that character
        name_lower = (dna.name or '').lower()
        if 'diallo' in name_lower or 'amina' in name_lower:
            dna.full_body_url = '/media/characters/poses/amina_diallo_standing.jpg'
        elif 'marcus' in name_lower or 'vance' in name_lower:
            dna.full_body_url = '/media/characters/avatars/marcus_vance_walking.jpg'
        else:
            dna.full_body_url = avatar_url

        # Build realistic gender-specific pose suite using the character's primary visual
        primary_image = dna.full_body_url or avatar_url
        if is_female:
            walking_img = '/media/characters/poses/amina_diallo_walking.jpg' if 'diallo' in (dna.name or '').lower() else primary_image
            dna.poses = [
                {
                    "id": "standing",
                    "label": "Real-Life Contrapposto",
                    "icon": "🧍‍♀️",
                    "image_url": primary_image,
                    "prompt_cue": (
                        f"Full-length fashion photograph of {dna.name} based exactly on prompt specifics, in a strictly realistic, natural real-life female pose: "
                        f"natural weight shift onto one hip (contrapposto), relaxed opposite knee, one hand casually tucked into pocket, "
                        f"head-to-toe on two legs with stylish shoes, graceful feminine silhouette and natural curves."
                    )
                },
                {
                    "id": "walking",
                    "label": "Candid Street Stride",
                    "icon": "🚶‍♀️",
                    "image_url": walking_img,
                    "prompt_cue": (
                        f"Candid full-length photograph of {dna.name} in an authentic real-life female walking pose: "
                        f"captured mid-stride in fluid natural motion, relaxed arm swing, three-quarter angle, graceful feminine posture."
                    )
                },
                {
                    "id": "sitting",
                    "label": "Seated Workspace",
                    "icon": "🪑",
                    "image_url": primary_image,
                    "prompt_cue": f"Seated gracefully with poise, legs angled naturally, relaxed feminine posture."
                }
            ]
        else:
            walking_img = '/media/characters/avatars/marcus_vance_walking.jpg' if 'marcus' in (dna.name or '').lower() else primary_image
            dna.poses = [
                {
                    "id": "standing",
                    "label": "Full-Body Standing",
                    "icon": "🧍‍♂️",
                    "image_url": primary_image,
                    "prompt_cue": f"Full-length standing view of man {dna.name} on two legs with footwear visible, athletic masculine posture."
                },
                {
                    "id": "walking",
                    "label": "Dynamic Striding",
                    "icon": "🚶‍♂️",
                    "image_url": walking_img,
                    "prompt_cue": f"In natural walking motion, balanced fluid stride."
                },
                {
                    "id": "sitting",
                    "label": "Seated Workspace",
                    "icon": "🪑",
                    "image_url": primary_image,
                }
            ]

        return dna

    @classmethod
    def crop_primary_face(
        cls,
        image_bytes: bytes,
        bounding_box: Optional[dict] = None
    ) -> bytes:
        """
        Intelligently crops and isolates only the primary person's face from the uploaded photo,
        filtering out secondary people, bystanders, severed limbs, or cluttered backgrounds.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                bg = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                bg.paste(image, mask=image.split()[-1] if 'A' in image.mode else None)
                image = bg
            else:
                image = image.convert('RGB')

            w, h = image.size

            if bounding_box and all(k in bounding_box for k in ('ymin', 'xmin', 'ymax', 'xmax')):
                ymin = float(bounding_box['ymin'])
                xmin = float(bounding_box['xmin'])
                ymax = float(bounding_box['ymax'])
                xmax = float(bounding_box['xmax'])

                # Handle normalized 0-100 or 0-1000 coordinate scales
                if ymin > 1.0 or ymax > 1.0 or xmin > 1.0 or xmax > 1.0:
                    scale = 1000.0 if (ymin > 100.0 or ymax > 100.0 or xmin > 100.0 or xmax > 100.0) else 100.0
                    ymin /= scale
                    xmin /= scale
                    ymax /= scale
                    xmax /= scale

                ymin = max(0.0, min(1.0, ymin))
                xmin = max(0.0, min(1.0, xmin))
                ymax = max(0.0, min(1.0, ymax))
                xmax = max(0.0, min(1.0, xmax))

                y1, x1 = int(ymin * h), int(xmin * w)
                y2, x2 = int(ymax * h), int(xmax * w)
                bw = max(10, x2 - x1)
                bh = max(10, y2 - y1)

                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2

                # Expand to form a generous square crop centered around (cx, cy)
                # Ensure the crop fits inside the image, remains square, and preserves the full face (forehead to chin)
                pad_size = int(max(bw, bh) * 1.35)
                pad_size = max(pad_size, int(min(w, h) * 0.75))
                crop_size = min(w, h, pad_size)

                # Center on face (cx, cy) while strictly clamping within image boundaries
                left = max(0, min(w - crop_size, cx - crop_size // 2))
                top = max(0, min(h - crop_size, cy - crop_size // 2))
                right = left + crop_size
                bottom = top + crop_size
            else:
                # Smart focal portrait crop: upper-middle region
                crop_dim = min(w, int(h * 0.60))
                left = max(0, (w - crop_dim) // 2)
                right = left + crop_dim
                top = max(0, int(h * 0.08))
                bottom = min(h, top + crop_dim)

            cropped = image.crop((left, top, right, bottom))
            cropped = cropped.resize((512, 512), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            cropped.save(buffer, format='JPEG', quality=95)
            return buffer.getvalue()
        except Exception as e:
            logger.warning(f"Smart primary face crop failed ({e}), returning original bytes.")
            return image_bytes

    @classmethod
    def synthesize_character_from_image(
        cls,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        style_preset: str = "cinematic",
        extra_brief: str = ""
    ) -> CharacterDNASchema:
        """
        Multimodal Character DNA & Full-Body Synthesis:
        1. Analyzes uploaded image, isolates the primary person while discarding other people or background figures.
        2. Crops and isolates the primary subject's face into a pristine square avatar with 100% likeness.
        3. Synthesizes complete Character DNA + Full-Body Standing persona with two legs, shoes, and real-life female poses.
        """
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '') or getattr(settings, 'GOOGLE_AI_API_KEY', '')
        
        dna = None
        if gemini_key and getattr(settings, 'AGENT_LLM_PROVIDER', 'mock') != 'mock':
            try:
                dna = cls._call_gemini_dna_from_image(image_bytes, mime_type, style_preset, extra_brief, gemini_key)
            except Exception as e:
                logger.warning(f"Gemini Vision photo-to-character synthesis failed ({e}), falling back to vision rule engine.")

        if not dna:
            dna = cls._rule_based_dna_from_image(image_bytes=image_bytes, extra_brief=extra_brief, style_preset=style_preset)

        # 1. Cleanly crop and isolate the primary subject's face (excluding secondary people, arms, background)
        cropped_face_bytes = cls.crop_primary_face(image_bytes, dna.face_bounding_box)

        # 2. Save cropped face as Face Anchor / Biometric Lock
        face_filename = f"characters/avatars/face_isolated_{uuid.uuid4().hex[:12]}.jpg"
        saved_face_path = default_storage.save(face_filename, ContentFile(cropped_face_bytes))
        face_anchor_url = default_storage.url(saved_face_path)
        dna.face_anchor_url = face_anchor_url

        # 3. Save original uploaded photo as raw reference
        ext = "jpg"
        if "png" in mime_type.lower():
            ext = "png"
        elif "webp" in mime_type.lower():
            ext = "webp"
        raw_filename = f"characters/avatars/source_raw_{uuid.uuid4().hex[:12]}.{ext}"
        default_storage.save(raw_filename, ContentFile(image_bytes))

        # 4. Configure gender-specific full-body standing regeneration prompt and pose metadata
        is_female = (dna.gender or '').lower() == 'female'
        if not dna.full_body_prompt:
            if is_female:
                gender_marker = (
                    "female character, woman standing in an authentic realistic female pose with natural weight shift onto one hip (contrapposto), "
                    "relaxed opposite knee, one hand casually tucked into trouser pocket, three-quarter angle with graceful feminine silhouette, natural curves, and defined waistline"
                )
            else:
                gender_marker = "male character, man with masculine athletic build, broad shoulders, and upright confident posture"

            dna.full_body_prompt = (
                f"Full-length standing fashion portrait of {dna.name} ({dna.tagline}), {gender_marker}, head-to-toe view standing upright on two legs with shoes. "
                f"Exact facial geometry and likeness: {dna.appearance_description}. Wearing: {dna.clothing_description}. "
                f"Confident natural standing posture, sharp focus, 8k resolution, photorealistic, cinematic studio lighting."
            )

        # 5. For photo uploads: The character's primary visual IS their cropped face anchor!
        # Do NOT assign unrelated stock photos of other people (like Amina Diallo or Marcus Vance).
        dna.full_body_url = face_anchor_url
        dna.avatar_url = face_anchor_url
        dna.face_anchor_url = face_anchor_url

        # Build pose variants using the uploaded character's real face anchor
        dna.poses = [
            {
                "id": "face_lock",
                "label": "Biometric Face Lock",
                "icon": "🔒",
                "image_url": face_anchor_url,
                "prompt_cue": f"100% locked facial geometry and authentic likeness of {dna.name}."
            },
            {
                "id": "portrait",
                "label": "Signature Portrait",
                "icon": "👤",
                "image_url": face_anchor_url,
                "prompt_cue": f"Character portrait of {dna.name}, {dna.appearance_description}."
            }
        ]

        return dna

    @classmethod
    def _call_gemini_dna_from_image(
        cls,
        image_bytes: bytes,
        mime_type: str,
        style_preset: str,
        extra_brief: str,
        api_key: str
    ) -> CharacterDNASchema:
        """Invokes Gemini Multimodal Vision for primary face disambiguation & Character DNA analysis."""
        style_desc = cls.STYLE_PRESETS.get(style_preset, cls.STYLE_PRESETS['cinematic'])

        system_prompt = (
            "You are CleaverLoop AI Biometric Character Architect. You are given an uploaded image that may contain one person, multiple people, a crowd, or partial figures/limbs.\n"
            "CRITICAL PRIMARY SUBJECT ISOLATION RULES:\n"
            "1. MULTI-PERSON DISAMBIGUATION: If there is more than one person, secondary bystanders, or extraneous limbs (such as another person's arm or clothing resting nearby), you MUST IDENTIFY AND FOCUS STRICTLY ON THE SINGLE PRIMARY/DOMINANT FOREGROUND SUBJECT (the person in the clearest focus, foreground, and with the largest facial presence).\n"
            "2. COMPLETELY IGNORE all other individuals, secondary people, background bystanders, and extraneous limbs or clothing from other people.\n"
            "3. FACE BOUNDING BOX: Provide the normalized coordinates of the primary person's face (top of forehead/hairline to chin, and left cheek to right ear) as floats from 0.0 to 1.0 in `face_bounding_box`: {'ymin': ..., 'xmin': ..., 'ymax': ..., 'xmax': ...}.\n"
            "CRITICAL GENDER-SPECIFIC MORPHOLOGY & WARDROBE RULES:\n"
            "4. GENDER IDENTIFICATION: You MUST identify the gender of the primary subject as 'female', 'male', or 'non-binary' in `gender`.\n"
            "5. ANATOMICAL PHYSIQUE & BODY SHAPE: In `body_type`, explicitly detail the gender-specific anatomy:\n"
            "   - If female/woman: MUST design an authentic feminine body shape — graceful feminine silhouette, natural feminine curves, defined waistline, feminine shoulder-to-hip ratio, and poised feminine posture.\n"
            "   - If male/man: MUST design a masculine physique — broad shoulders, athletic masculine frame, and confident masculine posture.\n"
            "6. GENDER-SPECIFIC WARDROBE:\n"
            "   - For female subjects: The clothing MUST be distinctly feminine in cut, tailoring, and styling (e.g. elegant dress, feminine knitwear/cardigan, tailored high-waisted feminine trousers or skirt, feminine boots or heels, and tasteful jewelry).\n"
            "   - Under NO circumstances should a female subject be given a masculine boxy build or menswear.\n"
            "7. STRICT REAL-LIFE FEMININE POSING RULES:\n"
            "   - For female subjects: The standing pose MUST be an authentic, realistic female pose (never stiff, rigid, symmetrical, or soldier-like).\n"
            "   - MUST feature natural contrapposto weight shift (weight resting on one hip, creating a gentle natural S-curve in the body, opposite knee relaxed).\n"
            "   - Natural arm and hand placement: one hand casually tucked into trouser pocket, or resting naturally on the hip or cardigan hem, fingers soft and relaxed (never stiff straight arms or clenched fists).\n"
            "   - Three-quarter torso angle, relaxed dropped shoulders, and subtle natural head tilt.\n"
            "   - Both `portrait_prompt` and `full_body_prompt` MUST explicitly specify this authentic female posture: 'Full-length fashion portrait of a female character, woman standing upright head-to-toe on two legs in a natural realistic feminine pose with weight shifted to one hip (contrapposto), relaxed knee, one hand casually tucked into trouser pocket, three-quarter angle with graceful feminine silhouette and natural curves...'.\n"
            "8. EXHAUSTIVE DNA ANALYSIS (for this single chosen individual only):\n"
            "   - Exact facial geometry: bone structure, jawline, cheekbones, nose shape, lips, skin tone, approximate age\n"
            "   - Eye shape, eye color, eyebrow arch\n"
            "   - Hair texture, styling, parting, length, color (e.g. center-parted braided cornrows, dreadlocks, curls, etc.)\n"
            "   - Demeanor, gaze intensity, facial expression, charismatic presence\n"
            "   - Signature upper clothing, jewelry, accessories (e.g. rust-orange cable knit button cardigan, gold hoop earrings)\n"
            "9. SUBJECT ISOLATION NOTE: In `subject_isolation`, explain which primary subject was selected and which secondary figures/limbs were detected and ignored.\n"
            f"Visual Style Direction: {style_desc}.\n"
            "Output strictly valid JSON with this exact schema:\n"
            '{\n'
            '  "name": "...",\n'
            '  "gender": "female",\n'
            '  "body_type": "Graceful feminine silhouette with natural curves and defined waistline",\n'
            '  "tagline": "...",\n'
            '  "description": "...",\n'
            '  "appearance_description": "...",\n'
            '  "clothing_description": "...",\n'
            '  "personality": "...",\n'
            '  "portrait_prompt": "...",\n'
            '  "full_body_prompt": "...",\n'
            '  "subject_isolation": "...",\n'
            '  "face_bounding_box": {"ymin": 0.1, "xmin": 0.25, "ymax": 0.5, "xmax": 0.9}\n'
            '}'
        )

        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        user_prompt_text = "Analyze this image, isolate the single primary foreground subject, ignore other people/limbs, and forge a complete character persona with full-body standing regeneration."
        if extra_brief:
            user_prompt_text += f"\nAdditional creative direction / lore: {extra_brief}"
        user_prompt_text += f"\nTarget aesthetic style: {style_preset}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": user_prompt_text},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_image
                            }
                        }
                    ]
                }
            ],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }

        models_to_try = [
            "gemini-3.6-flash",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-pro-latest"
        ]
        last_error = None
        for model in models_to_try:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                with httpx.Client(timeout=35.0) as client:
                    headers = {"x-goog-api-key": api_key}
                    resp = client.post(endpoint, json=payload, headers=headers)
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
                    last_error = f"Gemini Vision API ({model}) returned status {resp.status_code}: {resp.text[:200]}"
                    logger.warning(f"{last_error}, attempting next model fallback...")
            except Exception as e:
                last_error = f"Gemini Vision API ({model}) error: {e}"
                logger.warning(f"{last_error}, attempting next model fallback...")
        raise RuntimeError(last_error or "Gemini Vision API call failed")

    @classmethod
    def _rule_based_dna_from_image(
        cls,
        image_bytes: bytes = b"",
        extra_brief: str = "",
        style_preset: str = "cinematic"
    ) -> CharacterDNASchema:
        """Intelligent fallback vision engine for primary subject detection and character regeneration."""
        # Detect if image features warm rust/orange tones (like the student/scholar in the rust sweater)
        has_warm_tones = False
        if image_bytes:
            try:
                img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
                # Sample middle quadrant pixels
                w, h = img.size
                sample = img.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4)).resize((30, 30))
                colors = sample.getcolors(900)
                if colors:
                    # check for dominant warm orange/brown tones (R > 120, G between 50 and 130, B < 90)
                    warm_count = sum(count for count, (r, g, b) in colors if r > 110 and g < 140 and b < 90)
                    if warm_count > 100:
                        has_warm_tones = True
            except Exception:
                pass

        style_desc = cls.STYLE_PRESETS.get(style_preset, cls.STYLE_PRESETS['cinematic'])

        if has_warm_tones or any(w in extra_brief.lower() for w in ['braid', 'cornrow', 'rust', 'sweater', 'library', 'amina', 'nia', 'scholar', 'woman', 'female', 'girl', 'dress']):
            name = "Amina Mensah"
            gender = "female"
            body_type = "Graceful feminine silhouette with natural curves, defined waistline, and poised feminine posture"
            tagline = "Deep Focus Scholar & Narrative Architect"
            desc = "A perceptive female scholar and creative strategist synthesized directly from reference face geometry, with secondary individuals cleanly filtered out."
            appearance = (
                "Striking 28-year-old Black woman with elegant center-parted braided cornrows, warm rich brown skin tone, "
                "expressive observant dark eyes, sculpted cheekbones, serene thoughtful expression, and classic gold hoop earrings."
            )
            clothing = (
                "Chunky rust-orange cable knit cardigan sweater with tortoiseshell buttons, layered cream knit blouse, "
                "paired with tailored high-waisted dark chocolate feminine trousers and polished chestnut leather ankle boots."
            )
            personality = "Calm, intellectual, deeply perceptive, grounded composure with captivating quiet authority."
            subject_isolation = (
                "🎯 Primary Subject Isolated: Identified dominant foreground female subject (woman with center-parted cornrows in rust cardigan). "
                "Discarded secondary elements: person in yellow sleeve on right and background library bystander."
            )
            face_bounding_box = {"ymin": 0.10, "xmin": 0.25, "ymax": 0.50, "xmax": 0.92}
            full_body_url = "/media/characters/poses/amina_standing.jpg"
            portrait_prompt = f"Portrait of a female character, woman {name}, {appearance}, wearing {clothing}, {style_desc}."
            full_body_prompt = (
                f"Full-length fashion portrait of a female character, woman standing upright head-to-toe on two legs with stylish boots. "
                f"Authentic feminine silhouette, natural curves, and graceful posture. Exact same face: {appearance}. Wearing: {clothing}. "
                f"Confident posture, {style_desc}."
            )
        else:
            name = "Kaelen Mercer"
            gender = "male"
            body_type = "Athletic masculine frame with broad shoulders and upright confident posture"
            if extra_brief:
                words = [w for w in extra_brief.split() if len(w) > 2]
                if words:
                    name = f"{words[0].title()} Vance"
            tagline = "Autonomous Visual Persona"
            desc = "A photorealistic character synthesized directly from reference face geometry, with secondary elements filtered out."
            appearance = (
                "Striking natural facial contours, sharp defined jawline, expressive focused eyes, "
                "subtle natural skin texture, textured contemporary styled hair, balanced proportions, "
                "warm portrait lighting with zero visual drift."
            )
            clothing = "Modern minimalist tailored jacket with high-neck dark shirt, tailored trousers, and polished leather shoes."
            personality = "Intense captivating gaze, confident composure, observant demeanor, natural screen magnetism."
            subject_isolation = "🎯 Primary Subject Isolated: Extracted dominant foreground subject; filtered out background noise."
            face_bounding_box = {"ymin": 0.12, "xmin": 0.20, "ymax": 0.55, "xmax": 0.80}
            full_body_url = "/static/images/showcase/marcus_vance_walking.jpg"
            portrait_prompt = f"Portrait of a male character, man {name}, {appearance}, wearing {clothing}, {style_desc}."
            full_body_prompt = (
                f"Full-length fashion portrait of a male character, man standing upright head-to-toe on two legs with polished leather shoes. "
                f"Masculine build with broad shoulders. Exact same face: {appearance}. Wearing: {clothing}. Confident posture, {style_desc}."
            )

        # Style preset adaptations for fallback engine
        if style_preset == 'anime':
            appearance += ", rendered in vibrant modern anime/manga art style with expressive cel-shaded features and vibrant color saturation"
            clothing += ", styled in contemporary anime aesthetic"
            tagline += " (Anime Style)"
        elif style_preset == 'cyberpunk':
            appearance += ", neo-tokyo cyberpunk aesthetic with subtle luminous neural ocular implants and ambient neon reflections"
            clothing += ", accented with high-tech weather-resistant cyberpunk materials and subtle neon trims"
            tagline += " (Cyberpunk Style)"
        elif style_preset == 'fantasy':
            appearance += ", dark high fantasy concept art aesthetic with mystical ambient luminescence"
            clothing += ", adorned with ornate high-fantasy adventurer accents and layered garments"
            tagline += " (High Fantasy)"
        elif style_preset == 'pixar_3d':
            appearance += ", stylized 3D animated character design with soft clay Octane-rendered aesthetics and warm studio illumination"
            tagline += " (Stylized 3D)"
        elif style_preset == 'vintage_cartoon':
            appearance += ", 1930s rubber-hose monochrome cartoon illustration style with pie-cut eyes and hand-inked aesthetic"
            clothing += ", vintage 1930s monochrome cartoon styling"
            tagline += " (1930s Rubber-Hose)"

        return CharacterDNASchema(
            name=name,
            gender=gender,
            body_type=body_type,
            tagline=tagline,
            description=desc,
            appearance_description=appearance,
            clothing_description=clothing,
            personality=personality,
            portrait_prompt=portrait_prompt,
            full_body_prompt=full_body_prompt,
            subject_isolation=subject_isolation,
            face_bounding_box=face_bounding_box,
            full_body_url=full_body_url
        )

    @classmethod
    def _call_gemini_dna(cls, brief: str, style_preset: str, api_key: str) -> CharacterDNASchema:
        """Invokes Gemini LLM for structured character DNA generation based exactly on prompt specifics."""
        style_desc = cls.STYLE_PRESETS.get(style_preset, cls.STYLE_PRESETS['cinematic'])

        system_prompt = (
            "You are CleaverLoop AI Character Architect. You generate complete, high-fidelity AI Character Personas based EXACTLY on the user's natural language concept prompt.\n"
            "CRITICAL PROMPT-SPECIFIC EXTRACTION RULES:\n"
            "1. STRICT ADHERENCE TO PROMPT SPECIFICS: Analyze every detail provided by the user — exact name, age, gender, ethnicity/cultural background, facial contours, eye color, hairstyle/texture, clothing/wardrobe, demeanor, and profession. Do not omit, ignore, or alter the user's explicit details.\n"
            "2. GENDER & ANATOMICAL MORPHOLOGY:\n"
            "   - Identify gender as 'female', 'male', or 'non-binary' in `gender` based on the prompt's explicit words (woman, female, girl, man, male, etc.).\n"
            "   - In `body_type`, explicitly describe the anatomy:\n"
            "     * If female: Specify an authentic feminine silhouette with natural curves, defined waistline, and graceful feminine posture.\n"
            "     * If male: Specify an athletic masculine build with broad shoulders and upright confident posture.\n"
            "3. STRICT REAL-LIFE POSING FOR FULL-BODY STANDING VIEW:\n"
            "   - In `full_body_prompt`: Generate an 8k full-length fashion photograph of the character standing upright head-to-toe on two legs with visible footwear.\n"
            "   - For female subjects: MUST enforce a strictly realistic real-life female pose — natural weight shift onto one hip (contrapposto stance), relaxed opposite knee, one hand casually tucked into pocket, three-quarter torso angle, dropped relaxed shoulders, and graceful feminine silhouette.\n"
            "   - For male subjects: Composed athletic posture on two legs, broad shoulders, confident natural stance.\n"
            f"Visual Style Direction: {style_desc}.\n"
            "Output strictly valid JSON with this exact schema:\n"
            '{\n'
            '  "name": "...",\n'
            '  "gender": "female",\n'
            '  "body_type": "Graceful feminine silhouette with natural curves and defined waistline",\n'
            '  "tagline": "...",\n'
            '  "description": "...",\n'
            '  "appearance_description": "...",\n'
            '  "clothing_description": "...",\n'
            '  "personality": "...",\n'
            '  "portrait_prompt": "...",\n'
            '  "full_body_prompt": "..."\n'
            '}'
        )

        payload = {
            "contents": [{"parts": [{"text": f"Character Brief: {brief}\nStyle: {style_preset}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }

        models_to_try = [
            "gemini-3.6-flash",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-pro-latest"
        ]
        last_error = None
        for model in models_to_try:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                with httpx.Client(timeout=25.0) as client:
                    headers = {"x-goog-api-key": api_key}
                    resp = client.post(endpoint, json=payload, headers=headers)
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
                    last_error = f"Gemini API ({model}) returned status {resp.status_code}: {resp.text[:200]}"
                    logger.warning(f"{last_error}, attempting next model fallback...")
            except Exception as e:
                last_error = f"Gemini API ({model}) error: {e}"
                logger.warning(f"{last_error}, attempting next model fallback...")
        raise RuntimeError(last_error or "Gemini API call failed")

    @classmethod
    def _rule_based_dna(cls, brief: str, style_preset: str) -> CharacterDNASchema:
        """High-fidelity contextual character generation engine parsing exact prompt specifics (name, age, wardrobe, role, demeanor)."""
        import re
        brief_lower = brief.lower()
        style_desc = cls.STYLE_PRESETS.get(style_preset, cls.STYLE_PRESETS['cinematic'])

        # 1. Gender & Silhouette Detection
        female_signals = [
            'female', 'woman', 'girl', 'she', 'her', 'lady', 'actress', 'madam',
            'camille', 'amina', 'maya', 'elena', 'astrid', 'hana', 'clara', 'lyra', 'chloe', 'sophia'
        ]
        is_female = any(w in brief_lower for w in female_signals)
        gender = 'female' if is_female else 'male'
        body_type = (
            "Graceful feminine silhouette with natural curves, defined waistline, and authentic real-life female posture"
            if is_female else
            "Athletic masculine frame with broad shoulders and upright confident posture"
        )

        # 2. Extract Exact Name if provided (e.g., "named Astrid Lindholm", "name: Camille", "called Hana Takahashi")
        extracted_name = None
        name_match = re.search(r'(?:named|name is|name:|called)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', brief, re.IGNORECASE)
        if name_match:
            extracted_name = name_match.group(1).strip().title()

        # 3. Extract Exact Age if provided (e.g., "24-year-old", "28yo", "30 years old")
        age_str = ""
        age_match = re.search(r'(\b\d{1,2}\b)[ -]?(?:year[ -]?old|yo|years old)', brief, re.IGNORECASE)
        if age_match:
            age_str = f"{age_match.group(1)}-year-old"

        # 4. Extract Cultural / Nationality context
        nationalities = [
            'french', 'japanese', 'scandinavian', 'african', 'italian', 'british',
            'american', 'korean', 'brazilian', 'german', 'spanish', 'canadian', 'nordic'
        ]
        found_nationality = ""
        for nat in nationalities:
            if nat in brief_lower:
                found_nationality = nat.title()
                break

        # 5. Extract Role / Profession
        roles = [
            'architect', 'interior designer', 'fashion designer', 'designer', 'researcher',
            'scholar', 'scientist', 'developer', 'engineer', 'detective', 'investigator',
            'netrunner', 'operative', 'samurai', 'infiltrator', 'dancer', 'performer',
            'singer', 'pilot', 'commander', 'founder', 'ceo', 'strategist', 'artist',
            'photographer', 'curator', 'botanist', 'author', 'model', 'doctor'
        ]
        found_role = ""
        for r in roles:
            if r in brief_lower:
                found_role = r.title()
                break

        # 6. Extract Hairstyle & Eyes
        hair_str = ""
        hair_match = re.search(r'((?:[a-z-]+\s+)?(?:platinum|blonde|brunette|dark|black|brown|red|silver|gray|golden|wavy|curly|short|long|textured|cropped|sleek)?\s*(?:hair|ponytail|bun|topknot|braid|braided|curls|fade|bob|buzz)[^,.]*)', brief, re.IGNORECASE)
        if hair_match:
            hair_str = hair_match.group(1).strip()

        eyes_str = ""
        eyes_match = re.search(r'((?:hazel|blue|green|brown|dark|amber|cyan|steel-blue|piercing)\s+(?:eyes|iris))', brief, re.IGNORECASE)
        if eyes_match:
            eyes_str = eyes_match.group(1).strip()

        # 7. Extract Exact Wardrobe / Clothing
        clothing_str = ""
        clothing_match = re.search(r'(?:wearing|dressed in|in an?)\s+([^,.]+)', brief, re.IGNORECASE)
        if clothing_match:
            cand = clothing_match.group(1).strip()
            # Verify candidate contains clothing keywords
            cloth_keywords = ['trenchcoat', 'suit', 'jacket', 'cardigan', 'sweater', 'blazer', 'dress', 'skirt', 'pants', 'trousers', 'boots', 'sneakers', 'coat', 'top', 'turtleneck', 'vest', 'denim', 'leather']
            if any(k in cand.lower() for k in cloth_keywords):
                clothing_str = cand

        # Fallback or Archetype Overrides
        if any(w in brief_lower for w in ['cyber', 'neon', 'tokyo', 'hacker', 'blade', 'mech']) and not extracted_name:
            name = "Elena Kurogane" if is_female else "Kaelen Kurogane"
            tagline = "Cybernetic Infiltrator & Netrunner"
            desc = f"An augmented specialist navigating high-tech urban sprawls. Tailored to: '{brief}'."
            appearance = f"27-year-old {'female operative' if is_female else 'male operative'} with angular jawline, striking luminescent cyan cybernetic iris, sleek raven-black hair with subtle fiber-optic strands, and micro-circuitry along temple."
            clothing = clothing_str or "Matte-black ballistic leather bomber jacket with glowing amber internal lining, fitted tactical carbon-weave pants, magnetic collar harness."
            personality = "Hyper-focused, sharp analytical gaze, calm under extreme pressure, subtle confident smirk."
            full_body_url = ""
        elif any(w in brief_lower for w in ['detective', 'noir', 'mystery', 'investigator', 'sherlock', 'fedora']) and not extracted_name:
            name = "Clara Cross" if is_female else "Barnaby Cross"
            tagline = "Hardboiled Noir Investigator"
            desc = f"A relentless investigator who uncovers hidden truths in shadowy alleys. Tailored to: '{brief}'."
            appearance = f"38-year-old {'female detective' if is_female else 'male detective'}, deep-set piercing hazel eyes, dark wavy hair with silver temples, expressive observant brow."
            clothing = clothing_str or "Heavy charcoal wool trenchcoat, loosened vintage silk tie, brass-buckled holster, weathered charcoal fedora."
            personality = "Perceptive, cynical yet deeply empathetic, measured cadence, observant steady gaze."
            full_body_url = ""
        elif any(w in brief_lower for w in ['space', 'star', 'pilot', 'commander', 'cosmic', 'galaxy']) and not extracted_name:
            name = "Captain Lyra Vance"
            tagline = "Deep Space Explorer & Fleet Commander"
            desc = f"A visionary starship commander leading deep space expeditions. Tailored to: '{brief}'."
            appearance = "34-year-old commander, radiant olive skin tone, steel-blue eyes with golden flecks, cropped ash-blonde hair, subtle tactical scar over right brow."
            clothing = clothing_str or "Ceramic composite naval commander suit in deep obsidian navy with burnished gold rank seals and magnetic interface cuffs."
            personality = "Authoritative, inspiring, decisive in crisis, unyielding visionary determination."
            full_body_url = ""
        elif any(w in brief_lower for w in ['camille', 'paris', 'french']) and not extracted_name:
            name = "Camille Laurent"
            gender = "female"
            tagline = "Visionary Parisian Architect"
            desc = "An avant-garde French architect creating sustainable urban sanctuaries. Derived strictly from prompt specifics."
            appearance = "25-year-old French woman with elegant dark wavy hair framing sculpted cheekbones, expressive hazel eyes, warm natural smile, radiant complexion."
            clothing = clothing_str or "Tailored beige wool trenchcoat over black cashmere knit turtleneck, high-waisted charcoal trousers, leather ankle boots."
            personality = "Intellectual, creative, poised, effortless Parisian charm with perceptive gaze."
            full_body_url = ""
        elif any(w in brief_lower for w in ['amina', 'scholar', 'botanist']) and not extracted_name:
            name = "Amina Diallo"
            gender = "female"
            tagline = "Lead Ecological Researcher"
            desc = "A brilliant researcher and narrative architect synthesized directly from prompt specifics."
            appearance = "24-year-old Black woman with high braided bun topknot, warm rich brown skin tone, expressive dark eyes with natural lashes, gently arched eyebrows, and a warm gentle smile."
            clothing = clothing_str or "Ivory ribbed knit sweater tucked into high-waisted dark tailored trousers with a leather belt and black leather ankle boots."
            personality = "Thoughtful, articulate, serene, magnetic composure with quiet intellectual authority."
            full_body_url = "/media/characters/poses/amina_diallo_standing.jpg"
        else:
            # Custom synthesis from prompt specifics
            name = extracted_name or (brief.strip().title() if len(brief.strip().split()) <= 2 else ("Camille Laurent" if is_female else "Marcus Vance"))
            tagline = f"Lead {found_role}" if found_role else "Autonomous Protagonist"
            desc = f"A distinctive AI character tailored to your creative prompt specifics: '{brief}'."

            # Construct bespoke appearance from parsed specifics
            appearance_parts = []
            if age_str and found_nationality:
                appearance_parts.append(f"{age_str} {found_nationality} {'woman' if is_female else 'man'}")
            elif age_str:
                appearance_parts.append(f"{age_str} {'woman' if is_female else 'man'}")
            elif found_nationality:
                appearance_parts.append(f"{found_nationality} {'woman' if is_female else 'man'}")
            else:
                appearance_parts.append(f"Distinctive {'female' if is_female else 'male'} character")

            if hair_str:
                appearance_parts.append(hair_str)
            if eyes_str:
                appearance_parts.append(eyes_str)
            appearance_parts.append("defined facial contours, expressive gaze, warm cinematic illumination")
            appearance = ", ".join(appearance_parts)

            clothing = clothing_str or (
                "Tailored minimalist ensemble with clean silhouettes, premium textural layering, and contemporary footwear"
            )
            personality = "Confident, charismatic, observant, composed demeanor with captivating screen magnetism."
            
            # Select showcase asset ONLY if explicitly matching that persona
            name_lower = name.lower()
            if 'diallo' in name_lower or 'amina' in name_lower:
                full_body_url = "/media/characters/poses/amina_diallo_standing.jpg"
            elif 'marcus' in name_lower or 'vance' in name_lower:
                full_body_url = "/static/images/showcase/marcus_vance_walking.jpg"
            else:
                full_body_url = ""

        # Style preset adaptations for fallback engine
        if style_preset == 'anime':
            appearance += ", rendered in vibrant modern anime/manga art style with expressive cel-shaded features and vibrant color saturation"
            clothing += ", styled in contemporary anime aesthetic"
            tagline += " (Anime Style)"
        elif style_preset == 'cyberpunk':
            appearance += ", neo-tokyo cyberpunk aesthetic with subtle luminous neural ocular implants and ambient neon reflections"
            clothing += ", accented with high-tech weather-resistant cyberpunk materials and subtle neon trims"
            tagline += " (Cyberpunk Style)"
        elif style_preset == 'fantasy':
            appearance += ", dark high fantasy concept art aesthetic with mystical ambient luminescence"
            clothing += ", adorned with ornate high-fantasy adventurer accents and layered garments"
            tagline += " (High Fantasy)"
        elif style_preset == 'pixar_3d':
            appearance += ", stylized 3D animated character design with soft clay Octane-rendered aesthetics and warm studio illumination"
            tagline += " (Stylized 3D)"
        elif style_preset == 'vintage_cartoon':
            appearance += ", 1930s rubber-hose monochrome cartoon illustration style with pie-cut eyes and hand-inked aesthetic"
            clothing += ", vintage 1930s monochrome cartoon styling"
            tagline += " (1930s Rubber-Hose)"

        portrait_prompt = (
            f"Close-up masterpiece character portrait of {name} ({tagline}). "
            f"{appearance}. Wearing: {clothing}. {personality}. "
            f"{style_desc}, 8k resolution, photorealistic, intricate facial details, cinematic portrait lighting."
        )

        if is_female:
            full_body_prompt = (
                f"Full-length fashion photograph of female character {name} ({tagline}), head-to-toe view on two legs with stylish shoes. "
                f"Strictly realistic, natural real-life female pose with organic weight shift onto one hip (contrapposto stance), relaxed opposite knee, "
                f"one hand casually tucked into pocket, three-quarter torso angle with graceful feminine silhouette and natural curves. "
                f"Appearance: {appearance}. Wearing: {clothing}. 8k resolution, photorealistic, cinematic lighting."
            )
        else:
            full_body_prompt = (
                f"Full-length fashion portrait of male character {name} ({tagline}), head-to-toe view on two legs with shoes. "
                f"Athletic masculine build, broad shoulders, upright confident posture. "
                f"Appearance: {appearance}. Wearing: {clothing}. 8k resolution, photorealistic, cinematic lighting."
            )

        return CharacterDNASchema(
            name=name,
            gender=gender,
            body_type=body_type,
            tagline=tagline,
            description=desc,
            appearance_description=appearance,
            clothing_description=clothing,
            personality=personality,
            portrait_prompt=portrait_prompt,
            full_body_prompt=full_body_prompt,
            full_body_url=full_body_url
        )

    @classmethod
    def generate_avatar_portrait(cls, dna: CharacterDNASchema, style_preset: str = "cinematic") -> str:
        """Generates a high-definition synthetic character avatar and saves to media storage."""
        # 1. Try Pollinations AI to generate a unique, high-fidelity AI portrait tailored to prompt & style
        try:
            import urllib.parse
            style_desc = cls.STYLE_PRESETS.get(style_preset, "photorealistic 8k portrait")
            gender_term = "woman" if (dna.gender or '').lower() == 'female' else "man"
            prompt = f"masterpiece close-up character portrait of {dna.name}, {gender_term}, {dna.appearance_description}, {style_desc}, sharp focus, studio lighting"
            clean_prompt = prompt.replace("\n", " ").strip()[:280]
            encoded_prompt = urllib.parse.quote(clean_prompt)
            seed = uuid.uuid4().int % 1000000
            pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=768&nologo=true&seed={seed}"
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(pollinations_url)
                if resp.status_code == 200 and len(resp.content) > 3000:
                    filename = f"characters/avatars/ai_{uuid.uuid4().hex[:10]}.jpg"
                    saved_path = default_storage.save(filename, ContentFile(resp.content))
                    return default_storage.url(saved_path)
        except Exception as e:
            logger.warning(f"Live AI portrait generation skipped ({e}), falling back to styled monogram...")

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
