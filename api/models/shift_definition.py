from beanie import Document
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, time
from bson import ObjectId

class ShiftDefinition(Document):
    hospital_id: ObjectId = Field(..., description="Reference to Hospital")
    code: str = Field(..., min_length=1, max_length=1, description="Shift code: M, E, N, G")
    name: str = Field(..., min_length=1, max_length=50, description="Shift name")
    start_time: time = Field(..., description="Shift start time")
    end_time: time = Field(..., description="Shift end time")
    load_factor: float = Field(..., gt=0, description="Load factor for ratio calculation")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "shift_definitions"
        indexes = [
            [("hospital_id", 1)],
            [("code", 1)],
            [("hospital_id", 1), ("code", 1)],  # Compound index
        ]
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('code')
    @classmethod
    def validate_code(cls, v):
        valid_codes = ['M', 'E', 'N', 'G']
        if v.upper() not in valid_codes:
            raise ValueError(f'Code must be one of: {valid_codes}')
        return v.upper()
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Shift name cannot be empty')
        return v.strip().title()
    
    def update_timestamp(self):
        self.updated_at = datetime.utcnow()
        return self

class ShiftDefinitionCreate(BaseModel):
    hospital_id: str
    code: str = Field(..., min_length=1, max_length=1)
    name: str = Field(..., min_length=1, max_length=50)
    start_time: time
    end_time: time
    load_factor: float = Field(..., gt=0)

class ShiftDefinitionUpdate(BaseModel):
    code: str = Field(None, min_length=1, max_length=1)
    name: str = Field(None, min_length=1, max_length=50)
    start_time: time = None
    end_time: time = None
    load_factor: float = Field(None, gt=0)

class ShiftDefinitionResponse(BaseModel):
    id: str
    hospital_id: str
    code: str
    name: str
    start_time: time
    end_time: time
    load_factor: float
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True