from beanie import Document
from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId

class CopilotChats(Document):
    user_id: ObjectId = Field(..., description="Reference to Staff")
    query: str = Field(..., min_length=1, description="User query")
    response: str = Field(..., min_length=1, description="AI response")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "copilot_chats"
        indexes = [
            [("user_id", 1)],
            [("created_at", -1)],
        ]
    
    class Config:
        arbitrary_types_allowed = True

class CopilotChatsCreate(BaseModel):
    user_id: str
    query: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)

class CopilotChatsUpdate(BaseModel):
    query: str = Field(None, min_length=1)
    response: str = Field(None, min_length=1)

class CopilotChatsResponse(BaseModel):
    id: str
    user_id: str
    query: str
    response: str
    created_at: datetime
    
    class Config:
        from_attributes = True