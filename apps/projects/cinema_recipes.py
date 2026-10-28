"""
Cinema Director Recipes, Camera & Lens Emulation, Lighting, and Color Grading Presets
for CleaverLoop Film Studio.
"""
from typing import Dict, Any, List

GENRE_RECIPES: List[Dict[str, Any]] = [
    {
        "id": "thriller",
        "name": "Psychological Thriller",
        "icon": "🕵️",
        "camera_body": "ARRI Alexa 65",
        "lens": "Anamorphic",
        "aperture": "f/1.4",
        "lighting": "Chiaroscuro",
        "color_palette": "Bleach Bypass",
        "camera_movement": "Slow Push In",
        "cue": "tense psychological thriller cinematography, high-contrast chiaroscuro shadows, anamorphic depth",
    },
    {
        "id": "scifi",
        "name": "Sci-Fi Odyssey",
        "icon": "🚀",
        "camera_body": "RED V-Raptor",
        "lens": "Anamorphic",
        "aperture": "f/4",
        "lighting": "Volumetric Fog",
        "color_palette": "Teal & Orange",
        "camera_movement": "Tracking Shot",
        "cue": "epic sci-fi widescreen cinematography, volumetric atmospheric haze, horizontal anamorphic lens flare",
    },
    {
        "id": "drama",
        "name": "Intimate Drama",
        "icon": "🎭",
        "camera_body": "ARRI Alexa 65",
        "lens": "Vintage",
        "aperture": "f/1.4",
        "lighting": "Natural Window",
        "color_palette": "Golden Hour",
        "camera_movement": "Static Tripod",
        "cue": "intimate character drama, soft natural window light, shallow depth of field, organic film grain",
    },
    {
        "id": "horror",
        "name": "Atmospheric Horror",
        "icon": "🕯️",
        "camera_body": "16mm Film",
        "lens": "Vintage",
        "aperture": "f/1.4",
        "lighting": "Chiaroscuro",
        "color_palette": "Cyber Matrix",
        "camera_movement": "Dutch Angle Tilt",
        "cue": "eerie atmospheric horror cinematography, unsettling shadow play, claustrophobic framing",
    },
    {
        "id": "action",
        "name": "Kinetic Action",
        "icon": "💥",
        "camera_body": "RED V-Raptor",
        "lens": "Spherical",
        "aperture": "f/4",
        "lighting": "Neon Rim",
        "color_palette": "Teal & Orange",
        "camera_movement": "Whip Pan",
        "cue": "high-octane kinetic action cinematography, crisp shutter motion, dynamic camera energy",
    },
    {
        "id": "romance",
        "name": "Poetic Romance",
        "icon": "🌹",
        "camera_body": "Panavision DXL2",
        "lens": "Vintage",
        "aperture": "f/1.4",
        "lighting": "Rembrandt",
        "color_palette": "Golden Hour",
        "camera_movement": "Orbit 360",
        "cue": "luminous poetic romance cinematography, warm golden backlight, creamy bokeh highlights",
    },
    {
        "id": "documentary",
        "name": "Cinema Verite Doc",
        "icon": "📽️",
        "camera_body": "16mm Film",
        "lens": "Spherical",
        "aperture": "f/11",
        "lighting": "Natural Window",
        "color_palette": "Vintage Sepia",
        "camera_movement": "Handheld Documentary",
        "cue": "authentic cinema verite documentary style, deep focus, organic handheld texture",
    },
]

ERA_PRESETS: List[Dict[str, str]] = [
    {"id": "1970s_grit", "name": "1970s Grit", "cue": "1970s New Hollywood 35mm celluloid film stock, halation, warm tungsten grain"},
    {"id": "1980s_vhs", "name": "1980s VHS / Retro", "cue": "1980s analog cinema aesthetic, subtle chromatic aberration, synthwave neon glow"},
    {"id": "1990s_indie", "name": "1990s Indie 16mm", "cue": "1990s independent cinema 16mm film texture, high contrast, raw street lighting"},
    {"id": "2000s_digital", "name": "2000s Early Digital", "cue": "2000s thriller high-shutter look, cool green-tinted shadows, crisp edge contrast"},
    {"id": "modern_anamorphic", "name": "Modern Anamorphic 8K", "cue": "modern IMAX 8K digital cinema, ultra-clean dynamic range, oval anamorphic bokeh"},
]

CAMERA_BODIES: List[Dict[str, str]] = [
    {"id": "ARRI Alexa 65", "name": "ARRI Alexa 65", "cue": "shot on ARRI Alexa 65 65mm large-format sensor, natural skin tones, 14-stop latitude"},
    {"id": "RED V-Raptor", "name": "RED V-Raptor 8K VV", "cue": "shot on RED V-Raptor 8K VistaVision, razor-sharp micro-contrast, vivid color science"},
    {"id": "Panavision DXL2", "name": "Panavision Millennium DXL2", "cue": "shot on Panavision Millennium DXL2, Light Iron color science, rich shadow roll-off"},
    {"id": "16mm Film", "name": "Arriflex 16SR (16mm Film)", "cue": "shot on Kodak Vision3 500T 16mm film stock, authentic photochemical grain"},
]

LENS_TYPES: List[Dict[str, str]] = [
    {"id": "Anamorphic", "name": "Panavision Anamorphic 2x", "cue": "2x anamorphic prime lens, cinematic horizontal streak flares, oval bokeh"},
    {"id": "Spherical", "name": "Zeiss Master Prime Spherical", "cue": "Zeiss Master Prime spherical lens, zero distortion, edge-to-edge optical sharpness"},
    {"id": "Vintage", "name": "Cooke Panchro Vintage Prime", "cue": "vintage Cooke Speed Panchro lens, warm veil glow, gentle focus falloff"},
]

APERTURES: List[Dict[str, str]] = [
    {"id": "f/1.4", "name": "f/1.4 (Shallow Bokeh)", "cue": "wide-open f/1.4 aperture, ultra-shallow depth of field, subject isolated from blurred background"},
    {"id": "f/4", "name": "f/4 (Balanced Narrative)", "cue": "f/4 narrative aperture, balanced subject focus with contextual background detail"},
    {"id": "f/11", "name": "f/11 (Deep Focus)", "cue": "f/11 deep focus aperture, foreground and distant background simultaneously tack-sharp"},
]

CAMERA_MOVEMENT_GROUPS: Dict[str, List[str]] = {
    "Basic": ["Static Tripod", "Pan Left", "Pan Right", "Tilt Up", "Tilt Down"],
    "Vertical": ["Crane Up", "Crane Down", "Pedestal Rise", "Pedestal Drop", "Low-Angle Hero"],
    "Zoom": ["Slow Push In", "Slow Pull Out", "Snap Zoom", "Dolly Zoom (Vertigo)", "Crash Zoom"],
    "Complex": ["Tracking Shot", "Steadicam Follow", "Orbit 360", "Arc Left", "Arc Right"],
    "Specialty": ["Handheld Documentary", "Dutch Angle Tilt", "Whip Pan", "FPV Walk-Through", "Over-the-Shoulder"],
    "Aerial": ["Drone Establishing Sweep", "Top-Down God's Eye", "High-Altitude Flyover"],
}

COLOR_PALETTES: List[Dict[str, Any]] = [
    {"id": "Teal & Orange", "name": "Teal & Orange Blockbuster", "swatches": ["#0D3B4C", "#1E7898", "#E87A24", "#F4B942"], "cue": "teal and orange blockbuster color grading"},
    {"id": "Bleach Bypass", "name": "Bleach Bypass Grit", "swatches": ["#1B1F24", "#4A525A", "#8E969E", "#D6CFC7"], "cue": "desaturated bleach-bypass silver-retention color grade"},
    {"id": "Neon Noir", "name": "Neon Noir Cyberpunk", "swatches": ["#0B0719", "#6B11B4", "#FF1E8E", "#00F0FF"], "cue": "neon noir magenta and electric cyan color grade"},
    {"id": "Golden Hour", "name": "Warm Golden Hour", "swatches": ["#3B1D11", "#8F431A", "#E68A2E", "#FDE08D"], "cue": "warm golden hour amber sunset color grade"},
    {"id": "Cyber Matrix", "name": "Phosphor Emerald", "swatches": ["#06140B", "#0F381E", "#1F7A40", "#68E390"], "cue": "moody emerald green matrix shadow tint"},
    {"id": "Vintage Sepia", "name": "Archive Warm Sepia", "swatches": ["#241A14", "#5C4332", "#A68263", "#E6D2B8"], "cue": "nostalgic warm archival sepia color tone"},
]

LIGHTING_PRESETS: List[Dict[str, str]] = [
    {"id": "Chiaroscuro", "name": "Chiaroscuro Low-Key", "cue": "dramatic low-key chiaroscuro lighting with deep shadows"},
    {"id": "Rembrandt", "name": "Rembrandt Key Light", "cue": "classic 45-degree Rembrandt key lighting with cheek triangle highlight"},
    {"id": "Volumetric Fog", "name": "Volumetric God Rays", "cue": "atmospheric volumetric fog pierced by directional god rays"},
    {"id": "High-Key Studio", "name": "High-Key Commercial", "cue": "bright soft-diffused high-key studio commercial lighting"},
    {"id": "Neon Rim", "name": "Dual Neon Rim Light", "cue": "intense bi-color neon rim lighting outlining the silhouette"},
    {"id": "Natural Window", "name": "Soft Natural Window", "cue": "organic diffused natural window light"},
]


def get_cinema_catalog() -> Dict[str, Any]:
    """Return full structured Cinema Director catalog for templates and APIs."""
    all_movements = []
    for group_name, moves in CAMERA_MOVEMENT_GROUPS.items():
        for m in moves:
            all_movements.append({"group": group_name, "name": m})
    return {
        "genres": GENRE_RECIPES,
        "eras": ERA_PRESETS,
        "camera_bodies": CAMERA_BODIES,
        "lenses": LENS_TYPES,
        "apertures": APERTURES,
        "camera_movement_groups": CAMERA_MOVEMENT_GROUPS,
        "all_camera_movements": all_movements,
        "color_palettes": COLOR_PALETTES,
        "lighting_presets": LIGHTING_PRESETS,
    }


def build_director_prompt_modifier(recipe: Dict[str, Any]) -> str:
    """Compile a structured Cinema Director recipe dict into a rich cinematography prompt suffix."""
    if not recipe or not isinstance(recipe, dict):
        return ""

    parts = []
    genre_id = recipe.get("genre", "")
    for g in GENRE_RECIPES:
        if g["id"] == genre_id or g["name"].lower() == str(genre_id).lower():
            parts.append(g["cue"])
            break

    era_id = recipe.get("era", "")
    for e in ERA_PRESETS:
        if e["id"] == era_id or e["name"].lower() == str(era_id).lower():
            parts.append(e["cue"])
            break

    body = recipe.get("camera_body", "")
    for b in CAMERA_BODIES:
        if b["id"] == body or b["name"] == body:
            parts.append(b["cue"])
            break
    else:
        if body:
            parts.append(f"shot on {body}")

    lens = recipe.get("lens", "")
    for l in LENS_TYPES:
        if l["id"] == lens or l["name"] == lens:
            parts.append(l["cue"])
            break
    else:
        if lens:
            parts.append(f"{lens} lens")

    aperture = recipe.get("aperture", "")
    for a in APERTURES:
        if a["id"] == aperture:
            parts.append(a["cue"])
            break

    movement = recipe.get("camera_movement", "")
    if movement:
        parts.append(f"{movement} camera movement")

    lighting = recipe.get("lighting", "")
    for lt in LIGHTING_PRESETS:
        if lt["id"] == lighting or lt["name"] == lighting:
            parts.append(lt["cue"])
            break
    else:
        if lighting:
            parts.append(f"{lighting} lighting")

    palette = recipe.get("color_palette", "")
    for cp in COLOR_PALETTES:
        if cp["id"] == palette or cp["name"] == palette:
            parts.append(cp["cue"])
            break
    else:
        if palette:
            parts.append(f"{palette} color palette")

    return ", ".join(parts)

