from beanie import Document
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Dict, Any
from bson import ObjectId

class HospitalRules(Document):
    hospital_id: ObjectId = Field(..., description="Reference to Hospital")
    rule_key: str = Field(..., min_length=1, max_length=100, description="Rule identifier")
    rule_value: Dict[str, Any] = Field(..., description="Rule configuration as JSON")
    description: str = Field(..., min_length=1, description="Rule description")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "hospital_rules"
        indexes = [
            [("hospital_id", 1)],
            [("rule_key", 1)],
            [("hospital_id", 1), ("rule_key", 1)],  # Compound index
        ]
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('rule_key')
    @classmethod
    def validate_rule_key(cls, v):
        if not v.strip():
            raise ValueError('Rule key cannot be empty')
        return v.strip().lower()
    
    def update_timestamp(self):
        self.updated_at = datetime.utcnow()
        return self

class HospitalRulesCreate(BaseModel):
    hospital_id: str
    rule_key: str = Field(..., min_length=1, max_length=100)
    rule_value: Dict[str, Any]
    description: str = Field(..., min_length=1)

class HospitalRulesUpdate(BaseModel):
    rule_key: str = Field(None, min_length=1, max_length=100)
    rule_value: Dict[str, Any] = None
    description: str = Field(None, min_length=1)

class HospitalRulesResponse(BaseModel):
    id: str
    hospital_id: str
    rule_key: str
    rule_value: Dict[str, Any]
    description: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True