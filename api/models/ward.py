from beanie import Document
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
from bson import ObjectId

def convert_hospital_id(hospital_id: str) -> ObjectId:
    """Convert string hospital_id to ObjectId"""
    try:
        return ObjectId(hospital_id)
    except Exception:
        raise ValueError('Invalid hospital_id format')

def convert_incharge_id(incharge_id: Optional[str]) -> Optional[ObjectId]:
    """Convert string incharge_id to ObjectId"""
    if incharge_id is None:
        return None
    try:
        return ObjectId(incharge_id)
    except Exception:
        raise ValueError('Invalid incharge_id format')

def validate_bed_nurse_ratio(bed_nurse_ratio: str) -> str:
    """Validate bed_nurse_ratio string format"""
    try:
        if ':' in bed_nurse_ratio:
            beds, nurses = bed_nurse_ratio.split(':')
            beds = int(beds.strip())
            nurses = int(nurses.strip())
            if beds <= 0 or nurses <= 0:
                raise ValueError('Beds and nurses must be positive numbers')
            return bed_nurse_ratio.strip()
        else:
            # If it's a number string, validate it's a valid number
            float(bed_nurse_ratio)
            return bed_nurse_ratio.strip()
    except Exception:
        raise ValueError('bed_nurse_ratio must be in format "beds:nurses" or a valid number')

def get_bed_nurse_ratio_as_float(bed_nurse_ratio: str) -> float:
    """Convert bed_nurse_ratio string to float for calculations"""
    try:
        if ':' in bed_nurse_ratio:
            beds, nurses = bed_nurse_ratio.split(':')
            beds = int(beds.strip())
            nurses = int(nurses.strip())
            if beds <= 0 or nurses <= 0:
                raise ValueError('Beds and nurses must be positive numbers')
            ratio = beds / nurses
            return round(ratio, 2)
        else:
            # If it's already a number string, convert to float
            return round(float(bed_nurse_ratio), 2)
    except Exception:
        raise ValueError('bed_nurse_ratio must be in format "beds:nurses" or a valid number')

class Ward(Document):
    hospital_id: ObjectId = Field(..., description="Reference to Hospital")
    name: str = Field(..., min_length=1, max_length=255, description="Ward name")
    total_beds: int = Field(..., gt=0, description="Total number of beds")
    bed_nurse_ratio: str = Field(..., description="Bed to nurse ratio in format 'beds:nurses'")
    description: Optional[str] = Field(default=None, description="Ward description (optional)")
    incharge_id: Optional[ObjectId] = Field(None, description="Reference to Staff (ward incharge)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "wards"
        indexes = [
            [("hospital_id", 1)],
            [("incharge_id", 1)],
            [("name", 1)],
        ]
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Ward name cannot be empty')
        return v.strip().title()
    
    def update_timestamp(self):
        self.updated_at = datetime.utcnow()
        return self

class WardCreateInput(BaseModel):
    hospital_id: str
    name: str = Field(..., min_length=1, max_length=255)
    total_beds: int = Field(..., gt=0)
    bed_nurse_ratio: str = Field(..., description="Bed to nurse ratio in format 'beds:nurses'")
    description: Optional[str] = Field(default=None)
    incharge_id: Optional[str] = None
    
    @field_validator('description', mode='before')
    @classmethod
    def empty_description_as_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
            return v
        return v

class WardCreate(BaseModel):
    hospital_id: ObjectId
    name: str = Field(..., min_length=1, max_length=255)
    total_beds: int = Field(..., gt=0)
    bed_nurse_ratio: str = Field(..., description="Bed to nurse ratio in format 'beds:nurses'")
    description: Optional[str] = Field(default=None)
    incharge_id: Optional[ObjectId] = None
    
    class Config:
        arbitrary_types_allowed = True

class WardUpdateInput(BaseModel):
    hospital_id: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    total_beds: Optional[int] = Field(None, gt=0)
    bed_nurse_ratio: Optional[str] = Field(None, description="Bed to nurse ratio in format 'beds:nurses'")
    description: Optional[str] = Field(None, min_length=1)
    incharge_id: Optional[str] = None

class WardUpdate(BaseModel):
    hospital_id: Optional[ObjectId] = None
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    total_beds: Optional[int] = Field(None, gt=0)
    bed_nurse_ratio: Optional[str] = Field(None, description="Bed to nurse ratio in format 'beds:nurses'")
    description: Optional[str] = Field(None, min_length=1)
    incharge_id: Optional[ObjectId] = None
    
    class Config:
        arbitrary_types_allowed = True

class WardResponse(BaseModel):
    id: str
    hospital_id: str
    name: str
    total_beds: int
    bed_nurse_ratio: float
    description: Optional[str] = None
    incharge_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True