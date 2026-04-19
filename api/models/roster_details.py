from beanie import Document
from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Literal
from bson import ObjectId


class TransferRecord(BaseModel):
    transfer_id: ObjectId = Field(..., description="Reference to the transfer event")
    direction: Literal["in", "out"] = Field(
        ..., description="Direction of the transfer relative to this roster"
    )
    staff_id: Optional[ObjectId] = Field(default=None, description="Reference to Staff")
    employee_id: Optional[str] = Field(default=None, description="Employee identifier in the roster map")
    day_index: str = Field(..., description="Day key inside the roster map")
    transfer_date: date = Field(..., description="Date of the transfer")
    from_shift: Optional[str] = Field(default=None, description="Shift code in source ward")
    to_shift: Optional[str] = Field(default=None, description="Shift code in destination ward")
    from_ward_id: Optional[ObjectId] = Field(default=None, description="Source ward for the transfer")
    to_ward_id: Optional[ObjectId] = Field(default=None, description="Destination ward for the transfer")
    staff_snapshot: Dict[str, Any] = Field(
        default_factory=dict, description="Captured staff metadata at the time of transfer"
    )
    created_by: Optional[ObjectId] = Field(default=None, description="User who initiated the transfer")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True

class RosterDetails(Document):
    roster_id: ObjectId = Field(..., description="Reference to Roster")
    roster_input: Dict[str, Any] = Field(..., description="Snapshot of generation input")
    roster: Dict[str, Any] = Field(..., description="Actual roster data")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "roster_details"
        indexes = [
            [("roster_id", 1)],
            [("date", 1)],
            [("roster_id", 1), ("date", 1)],  # Compound index
        ]
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }
    
    def update_timestamp(self):
        self.updated_at = datetime.utcnow()
        return self

class RosterDetailsCreate(BaseModel):
    roster_id: ObjectId
    roster_input: Dict[str, Any]
    roster: Dict[str, Any]

    class Config:
        arbitrary_types_allowed = True

class RosterDetailsUpdate(BaseModel):
    roster_input: Dict[str, Any] = None
    roster: Dict[str, Any] = None

class RosterDetailsResponse(BaseModel):
    id: str
    roster_id: str
    roster_input: Dict[str, Any]
    roster: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True