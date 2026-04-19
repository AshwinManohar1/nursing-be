from beanie import Document, Indexed
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from typing import Dict, Any, Optional

class WardOccupancy(Document):
    hospital_id: str
    ward_name: str
    report_date: date
    report_time: datetime
    shift: str = Field(..., description="Derived shift: M, E, N")  # Add this field
    total_beds: int = Field(..., ge=0)
    open_beds: int = Field(..., ge=0)
    previous_day_total: int = Field(..., ge=0)
    new_admission: int = Field(..., ge=0)
    transfer_in: int = Field(..., ge=0)
    transfer_out: int = Field(..., ge=0)
    marked_for_discharge: int = Field(..., ge=0)
    normal_discharges: int = Field(..., ge=0)
    lama: int = Field(..., ge=0)
    deaths: int = Field(..., ge=0)
    others: int = Field(..., ge=0)
    total_present: int = Field(..., ge=0)
    bed_occupancy_rate: float = Field(..., ge=0, le=100)
    source: str
    raw_data: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "ward_occupancy"  # Collection name in MongoDB
        indexes = [
            [("hospital_id", 1), ("ward_name", 1), ("report_date", -1)],  # Compound index for efficient queries
            [("report_date", -1)],  # Index on report_date descending
            [("hospital_id", 1)],  # Index on hospital_id
        ]
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('source')
    @classmethod
    def validate_source(cls, v):
        valid_sources = ['manual', 'integration', 'api']
        if v not in valid_sources:
            raise ValueError(f'Source must be one of: {valid_sources}')
        return v
    
    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.utcnow()
        return self

class WardOccupancyCreate(BaseModel):
    hospital_id: str
    ward_name: str
    report_date: date
    report_time: datetime
    shift: str = Field(..., description="Derived shift: M, E, N")  # Add this field
    total_beds: int = Field(..., ge=0)
    open_beds: int = Field(..., ge=0)
    previous_day_total: int = Field(..., ge=0)
    new_admission: int = Field(..., ge=0)
    transfer_in: int = Field(..., ge=0)
    transfer_out: int = Field(..., ge=0)
    marked_for_discharge: int = Field(..., ge=0)
    normal_discharges: int = Field(..., ge=0)
    lama: int = Field(..., ge=0)
    deaths: int = Field(..., ge=0)
    others: int = Field(..., ge=0)
    total_present: int = Field(..., ge=0)
    bed_occupancy_rate: float = Field(..., ge=0, le=100)
    source: str
    raw_data: Dict[str, Any]

class WardOccupancyUpdate(BaseModel):
    report_date: date = None
    report_time: datetime = None
    shift: str = Field(..., description="Derived shift: M, E, N")  # Add this field
    total_beds: int = Field(None, ge=0)
    open_beds: int = Field(None, ge=0)
    previous_day_total: int = Field(None, ge=0)
    new_admission: int = Field(None, ge=0)
    transfer_in: int = Field(None, ge=0)
    transfer_out: int = Field(None, ge=0)
    marked_for_discharge: int = Field(None, ge=0)
    normal_discharges: int = Field(None, ge=0)
    lama: int = Field(None, ge=0)
    deaths: int = Field(None, ge=0)
    others: int = Field(None, ge=0)
    total_present: int = Field(None, ge=0)
    bed_occupancy_rate: float = Field(None, ge=0, le=100)
    source: str = None
    raw_data: Dict[str, Any] = None

class WardOccupancyResponse(BaseModel):
    id: str
    hospital_id: str
    ward_name: str
    report_date: date
    report_time: datetime
    shift: str
    total_beds: int
    open_beds: int
    previous_day_total: int
    new_admission: int
    transfer_in: int
    transfer_out: int
    marked_for_discharge: int
    normal_discharges: int
    lama: int
    deaths: int
    others: int
    total_present: int
    bed_occupancy_rate: float
    source: str
    raw_data: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True