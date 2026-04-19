from beanie import Document, Indexed
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
from bson import ObjectId

class Hospital(Document):
    name: str = Field(..., min_length=1, max_length=255, description="Hospital name")
    address: str = Field(..., min_length=1, description="Hospital address")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "hospitals"  # Collection name in MongoDB
        indexes = [
            [("name", 1)],  # Index on name for faster queries
            [("created_at", -1)],  # Index on created_at descending
        ]
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Hospital name cannot be empty')
        return v.strip().title()  # Capitalize first letter of each word
    
    @field_validator('address')
    @classmethod
    def validate_address(cls, v):
        if not v.strip():
            raise ValueError('Hospital address cannot be empty')
        return v.strip()
    
    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.utcnow()
        return self

# Create/Update models for API
class HospitalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1)

class HospitalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = Field(None, min_length=1)

class HospitalResponse(BaseModel):
    id: str
    name: str
    address: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True