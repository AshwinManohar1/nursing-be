from beanie import Document
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any
from bson import ObjectId

class CopilotActions(Document):
    roster_id: ObjectId = Field(..., description="Reference to Roster")
    user_id: ObjectId = Field(..., description="Reference to Staff")
    ai_response: str = Field(..., min_length=1, description="AI response text")
    action_json: Dict[str, Any] = Field(..., description="Action data as JSON")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "copilot_actions"
        indexes = [
            [("roster_id", 1)],
            [("user_id", 1)],
            [("created_at", -1)],
        ]
    
    class Config:
        arbitrary_types_allowed = True

class CopilotActionsCreate(BaseModel):
    roster_id: str
    user_id: str
    ai_response: str = Field(..., min_length=1)
    action_json: Dict[str, Any]

class CopilotActionsUpdate(BaseModel):
    ai_response: str = Field(None, min_length=1)
    action_json: Dict[str, Any] = None

class CopilotActionsResponse(BaseModel):
    id: str
    roster_id: str
    user_id: str
    ai_response: str
    action_json: Dict[str, Any]
    created_at: datetime
    
    class Config:
        from_attributes = True