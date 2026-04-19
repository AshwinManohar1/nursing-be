from beanie import Document
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from typing import Dict, Any, Optional
from bson import ObjectId
from enum import Enum

class RosterStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DELETED = "deleted"

class Roster(Document):
    ward_id: Optional[ObjectId] = Field(None, description="Reference to Ward")
    created_by: Optional[ObjectId] = Field(None, description="Reference to Staff (creator)")
    approved_by: Optional[ObjectId] = Field(None, description="Reference to Staff (approver)")
    period_start: date = Field(..., description="Roster period start date")
    period_end: date = Field(..., description="Roster period end date")
    status: RosterStatus = Field(default=RosterStatus.DRAFT, description="Roster status")
    name: str = Field(..., min_length=1, description="Roster name")
    comments: Optional[str] = Field(None, description="Roster comments")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "rosters"
        indexes = [
            [("ward_id", 1)],
            [("created_by", 1)],
            [("approved_by", 1)],
            [("status", 1)],
            [("period_start", 1)],
            [("period_end", 1)],
        ]
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if isinstance(v, str):
            try:
                return RosterStatus(v)
            except ValueError:
                raise ValueError(f'Status must be one of: {[status.value for status in RosterStatus]}')
        return v
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Roster name cannot be empty')
        return v.strip()
    
    @field_validator('period_end')
    @classmethod
    def validate_period_end(cls, v, info):
        if 'period_start' in info.data and v <= info.data['period_start']:
            raise ValueError('Period end must be after period start')
        return v
    
    def update_timestamp(self):
        self.updated_at = datetime.utcnow()
        return self

class RosterCreate(BaseModel):
    ward_id: Optional[str] = None
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    period_start: date
    period_end: date
    status: RosterStatus = RosterStatus.DRAFT
    name: str = Field(..., min_length=1)
    comments: Optional[str] = None

class RosterUpdate(BaseModel):
    ward_id: Optional[str] = None
    approved_by: Optional[str] = None
    period_start: date = None
    period_end: date = None
    status: Optional[RosterStatus] = None
    name: str = Field(None, min_length=1)
    comments: Optional[str] = None

class RosterResponse(BaseModel):
    id: str
    ward_id: Optional[str] = None
    created_by: str
    approved_by: Optional[str] = None
    period_start: date
    period_end: date
    status: RosterStatus
    name: str
    comments: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True