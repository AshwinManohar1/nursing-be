from beanie import Document, Indexed
from pydantic import BaseModel, Field, field_validator, EmailStr
from datetime import datetime
from typing import List, Optional
from bson import ObjectId

class Staff(Document):
    name: str = Field(..., min_length=1, max_length=255, description="Staff member name")
    email: Optional[EmailStr] = Field(default=None, description="Staff email address (optional)")
    contact_no: Optional[str] = Field(default=None, description="Staff contact number (optional)")
    emp_id: Indexed(str, unique=True) = Field(..., description="Employee ID")
    grade: Optional[str] = Field(default=None, description="Staff grade (N1-N8, optional)")
    position: str = Field(..., min_length=1, description="Staff position")
    gender: Optional[str] = Field(default=None, description="Staff gender")
    hospital_id: ObjectId = Field(..., description="Reference to Hospital")
    ward_id: Optional[List[ObjectId]] = Field(default=None, description="List of ward IDs")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "staff"
        indexes = [
            [("email", 1)],
            [("emp_id", 1)],
            [("hospital_id", 1)],
            [("grade", 1)],
            [("ward_id", 1)],
        ]
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Staff name cannot be empty')
        return v.strip().title()
    
    @field_validator('grade')
    @classmethod
    def validate_grade(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if not v:  # Empty string after stripping
                return None
        if not v.startswith('N') or not v[1:].isdigit() or int(v[1:]) not in range(1, 9):
            raise ValueError('Grade must be N1-N8')
        return v.upper()

    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip().upper()
            # Normalize to MALE/FEMALE/OTHER
            if v in ['MALE', 'M']:
                return 'MALE'
            elif v in ['FEMALE', 'F']:
                return 'FEMALE'
            elif v == 'OTHER':
                return 'OTHER'
            else:
                # Invalid value - you might want to raise an error or return None
                raise ValueError(f"Gender must be one of: MALE, FEMALE, OTHER (or M, F)")
        return v
    
    @field_validator('contact_no')
    @classmethod
    def validate_contact_no(cls, v):
        if v is None:
            return None
        if not v.strip():
            return None
        # Basic validation for contact number (can be enhanced based on requirements)
        cleaned = ''.join(filter(str.isdigit, v))
        if len(cleaned) < 10:
            raise ValueError('Contact number must be at least 10 digits')
        return v.strip()
    
    @field_validator('emp_id')
    @classmethod
    def validate_emp_id(cls, v):
        if not v.strip():
            raise ValueError('Employee ID cannot be empty')
        return v.strip()
    
    @field_validator('position')
    @classmethod
    def validate_position(cls, v):
        if not v or not v.strip():
            raise ValueError('Position cannot be empty')
        v_lower = v.strip().lower()
        valid_positions = ['ward_incharge', 'staff_nurse', 'admin', 'shift_incharge']
        if v_lower not in valid_positions:
            raise ValueError(f'Position must be one of: {valid_positions}')
        return v_lower
    
    def update_timestamp(self):
        self.updated_at = datetime.utcnow()
        return self

class StaffCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    contact_no: Optional[str] = None
    emp_id: str
    gender: str
    grade: Optional[str] = None
    position: str = Field(..., min_length=1)
    hospital_id: str
    ward_id: Optional[List[str]] = None

    @field_validator('email', mode='before')
    @classmethod
    def empty_email_as_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
    
    @field_validator('grade', mode='before')
    @classmethod
    def empty_grade_as_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
    
    @field_validator('contact_no', mode='before')
    @classmethod
    def empty_contact_no_as_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
    
    @field_validator('position')
    @classmethod
    def validate_position(cls, v):
        if not v or not v.strip():
            raise ValueError('Position cannot be empty')
        v_lower = v.strip().lower()
        valid_positions = ['ward_incharge', 'staff_nurse', 'admin', 'shift_incharge']
        if v_lower not in valid_positions:
            raise ValueError(f'Position must be one of: {valid_positions}')
        return v_lower

    @field_validator('hospital_id')
    @classmethod
    def validate_hospital_id(cls, v):
        if not v or not v.strip():
            raise ValueError('hospital_id is required')
        return v.strip()

class StaffUpdate(BaseModel):
    name: str = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    contact_no: str = None
    emp_id: str = None
    gender: Optional[str] = None
    grade: str = None
    position: str = Field(None, min_length=1)
    hospital_id: str = None
    ward_id: Optional[List[str]] = None

    @field_validator('email', mode='before')
    @classmethod
    def empty_email_as_none_update(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
    
    @field_validator('position')
    @classmethod
    def validate_position(cls, v):
        if v is None:
            return v
        if not v.strip():
            raise ValueError('Position cannot be empty')
        v_lower = v.strip().lower()
        valid_positions = ['ward_incharge', 'staff_nurse', 'admin', 'shift_incharge']
        if v_lower not in valid_positions:
            raise ValueError(f'Position must be one of: {valid_positions}')
        return v_lower

class StaffResponse(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    contact_no: Optional[str] = None
    emp_id: str
    grade: Optional[str] = None
    position: str
    gender: Optional[str] = None
    hospital_id: str
    ward_id: Optional[List[str]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True