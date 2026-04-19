from beanie import Document
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
from bson import ObjectId

class User(Document):
    employee_id: str = Field(..., unique=True, description="Employee ID for login")
    salt: str = Field(..., description="Password salt")
    password_hash: str = Field(..., description="Hashed password")
    role: str = Field(..., description="User role")
    staff_id: Optional[ObjectId] = Field(None, description="Reference to Staff (required for ADMIN, WARD_INCHARGE, and STAFF; optional only for SUPER_ADMIN)")
    status: str = Field(default="PENDING", description="User status")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "users"
        indexes = [
            [("employee_id", 1)],  # Unique index for login
            [("staff_id", 1)],
            [("role", 1)],
            [("status", 1)],
        ]
    
    class Config:
        arbitrary_types_allowed = True

    @field_validator('employee_id')
    @classmethod
    def validate_employee_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Employee ID cannot be empty')
        return v.strip()
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        v_upper = v.upper() if isinstance(v, str) else v
        valid_roles = ['SUPER_ADMIN', 'ADMIN', 'WARD_INCHARGE', 'STAFF']
        if v_upper not in valid_roles:
            raise ValueError(f'Role must be one of: {valid_roles}')
        return v_upper
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        v_upper = v.upper() if isinstance(v, str) else v
        valid_statuses = ['PENDING', 'ACTIVE', 'SUSPENDED', 'LOCKED']
        if v_upper not in valid_statuses:
            raise ValueError(f'Status must be one of: {valid_statuses}')
        return v_upper
    
    def update_timestamp(self):
        self.updated_at = datetime.utcnow()
        return self

class UserCreate(BaseModel):
    employee_id: str = Field(..., description="Employee ID for login")
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    role: str
    staff_id: Optional[str] = None
    
    @field_validator('employee_id')
    @classmethod
    def validate_employee_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Employee ID cannot be empty')
        return v.strip()
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        v_upper = v.upper() if isinstance(v, str) else v
        valid_roles = ['SUPER_ADMIN', 'ADMIN', 'WARD_INCHARGE', 'STAFF']
        if v_upper not in valid_roles:
            raise ValueError(f'Role must be one of: {valid_roles}')
        return v_upper

class UserUpdate(BaseModel):
    employee_id: Optional[str] = None
    role: Optional[str] = None
    staff_id: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, description="Password must be at least 8 characters")
    
    @field_validator('employee_id')
    @classmethod
    def validate_employee_id(cls, v):
        if v is None:
            return v
        if not v.strip():
            raise ValueError('Employee ID cannot be empty')
        return v.strip()
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v is None:
            return v
        v_upper = v.upper() if isinstance(v, str) else v
        valid_roles = ['SUPER_ADMIN', 'ADMIN', 'WARD_INCHARGE', 'STAFF']
        if v_upper not in valid_roles:
            raise ValueError(f'Role must be one of: {valid_roles}')
        return v_upper
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        v_upper = v.upper() if isinstance(v, str) else v
        valid_statuses = ['PENDING', 'ACTIVE', 'SUSPENDED', 'LOCKED']
        if v_upper not in valid_statuses:
            raise ValueError(f'Status must be one of: {valid_statuses}')
        return v_upper

class UserLogin(BaseModel):
    employee_id: str = Field(..., description="Employee ID for login")
    password: str = Field(..., description="Password")
    
    @field_validator('employee_id')
    @classmethod
    def validate_employee_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Employee ID cannot be empty')
        return v.strip()

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token")

class UserResponse(BaseModel):
    id: str
    employee_id: str
    role: str
    staff_id: Optional[str] = None
    status: str
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True