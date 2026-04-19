from beanie import Document
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
from bson import ObjectId

class Notification(Document):
    user_id: ObjectId = Field(..., description="Reference to Staff")
    type: str = Field(..., description="Notification type")
    roster_id: Optional[ObjectId] = Field(None, description="Reference to Roster")
    message: str = Field(..., min_length=1, description="Notification message")
    is_read: bool = Field(default=False, description="Read status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "notifications"
        indexes = [
            [("user_id", 1)],
            [("roster_id", 1)],
            [("type", 1)],
            [("is_read", 1)],
            [("created_at", -1)],
        ]
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        valid_types = ['approval_request', 'roster_changed', 'comment_added']
        if v not in valid_types:
            raise ValueError(f'Type must be one of: {valid_types}')
        return v

class NotificationCreate(BaseModel):
    user_id: str
    type: str
    roster_id: Optional[str] = None
    message: str = Field(..., min_length=1)
    is_read: bool = False

class NotificationUpdate(BaseModel):
    type: str = None
    roster_id: Optional[str] = None
    message: str = Field(None, min_length=1)
    is_read: bool = None

class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str
    roster_id: Optional[str] = None
    message: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True