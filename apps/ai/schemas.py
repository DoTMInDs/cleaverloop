from typing import List, Optional
from pydantic import BaseModel, Field

class CharacterCastMember(BaseModel):
    name: str = Field(..., max_length=120)
    role: str = Field(default="Lead Protagonist", max_length=100)
    description: str = Field(default="")
    appearance_cue: str = Field(default="")
    avatar_icon: Optional[str] = Field(default="👤")

class StoryboardScenePlan(BaseModel):
    order: int
    title: str = Field(..., max_length=120)
    prompt: str = Field(..., description="Generative AI prompt for the video scene")
    duration: int = Field(default=5, ge=3, le=15, description="Scene duration in seconds")
    camera_direction: Optional[str] = Field(default="", max_length=100)
    visual_style: Optional[str] = Field(default="", max_length=100)
    dialogue: Optional[str] = Field(default="")
    character_name: Optional[str] = Field(default="")
    character_action: Optional[str] = Field(default="")
    model_preference: str = Field(default="automatic")

class StoryboardPlan(BaseModel):
    project_title: str = Field(..., max_length=150)
    project_description: str = Field(default="")
    aspect_ratio: str = Field(default="16:9")
    characters: List[CharacterCastMember] = Field(default_factory=list)
    selected_character_id: Optional[str] = Field(default=None)
    scenes: List[StoryboardScenePlan]
    estimated_total_duration: int = 0
    estimated_total_credits: int = 0
