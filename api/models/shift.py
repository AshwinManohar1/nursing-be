from pydantic import BaseModel, Field
from typing import Optional
from datetime import time

class Shift(BaseModel):
    code: str
    name: str
    hours: int
    start_time: str
    end_time: str
    break_minutes: int

class ShiftCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name of the shift")
    start_time: time = Field(..., description="Start time of the shift")
    end_time: time = Field(..., description="End time of the shift")
    description: Optional[str] = Field(None, description="Description of the shift")

class ShiftUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Name of the shift")
    start_time: Optional[time] = Field(None, description="Start time of the shift")
    end_time: Optional[time] = Field(None, description="End time of the shift")
    description: Optional[str] = Field(None, description="Description of the shift")