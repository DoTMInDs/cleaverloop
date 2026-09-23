from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class CharacterDNASchema(BaseModel):
    name: str = Field(..., max_length=120, description="Character full name or alias")
    tagline: str = Field(default="Protagonist", max_length=120, description="Role or archetype title")
    description: str = Field(default="", description="Short lore, backstory or bio")
    appearance_description: str = Field(..., description="Detailed facial geometry, eye color, hairstyle, age, build, and skin tone")
    clothing_description: str = Field(default="", description="Signature wardrobe, outfit, accessories, and color scheme")
    personality: str = Field(default="", description="Mannerisms, facial expressions, attitude, and gaze")
    portrait_prompt: str = Field(..., description="Optimized text-to-image prompt for generating the character avatar")
    avatar_url: Optional[str] = Field(default=None, description="URL or data URI of the generated avatar image")
    
    # Intelligent Multi-Person Disambiguation & Full-Body Regeneration Fields
    subject_isolation: Optional[str] = Field(
        default="",
        description="Explanation of the primary subject chosen and secondary figures/limbs ignored"
    )
    face_bounding_box: Optional[Dict[str, float]] = Field(
        default=None,
        description="Normalized coordinates {'ymin', 'xmin', 'ymax', 'xmax'} of the isolated primary face"
    )
    face_anchor_url: Optional[str] = Field(
        default=None,
        description="URL of the cleanly isolated, cropped face avatar"
    )
    full_body_prompt: Optional[str] = Field(
        default="",
        description="Full-body standing prompt with two legs and shoes visible for complete character regeneration"
    )
    full_body_url: Optional[str] = Field(
        default=None,
        description="URL of the regenerated full-length standing figure"
    )
    # Gender-Specific Identification & Morphology Fields
    gender: Optional[str] = Field(
        default="female",
        description="Identified gender of the character: 'female', 'male', or 'non-binary'"
    )
    body_type: Optional[str] = Field(
        default="",
        description="Gender-specific body shape: feminine silhouette with natural curves, masculine athletic frame, etc."
    )
    poses: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Pre-configured pose variants for the regenerated character"
    )

