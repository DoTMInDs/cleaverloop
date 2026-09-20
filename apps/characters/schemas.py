from typing import Optional
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
