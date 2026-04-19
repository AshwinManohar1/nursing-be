from beanie import Document
from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, Literal
from bson import ObjectId

class WardTransfer(Document):
    hospital_id: ObjectId = Field(...)
    staff_id: ObjectId = Field(...)
    employee_id: str = Field(..., description="Denormalized emp_id")
    transfer_date: date = Field(...)
    from_shift: str = Field(..., description="Shift code in source ward (e.g., M/E/N/G)")
    to_shift: str = Field(..., description="Shift code in destination ward (e.g., M/E/N/G)")
    from_ward_id: ObjectId = Field(...)
    to_ward_id: ObjectId = Field(...)
    roster_id: ObjectId = Field(..., description="Source roster document")
    roster_details_id: ObjectId = Field(..., description="Source roster details document")
    destination_roster_id: Optional[ObjectId] = Field(None)
    destination_roster_details_id: Optional[ObjectId] = Field(None)
    status: Literal["pending", "applied", "cancelled"] = Field(default="pending")
    remarks: Optional[str] = Field(None, description="Optional remarks/notes for the transfer")
    created_by: ObjectId = Field(...)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "ward_transfers"
        indexes = [
            [("hospital_id", 1), ("transfer_date", 1)],
            [("from_ward_id", 1), ("transfer_date", 1)],
            [("to_ward_id", 1), ("transfer_date", 1)],
            [("staff_id", 1), ("transfer_date", 1), ("from_shift", 1)],
            [("status", 1), ("transfer_date", 1)]
        ]

    class Config:
        arbitrary_types_allowed = True

    def update_timestamp(self):
        self.updated_at = datetime.utcnow()
        return self


class WardTransferCreate(BaseModel):
    hospital_id: str
    staff_id: str
    employee_id: str
    transfer_date: date
    from_shift: str
    to_shift: str
    from_ward_id: str
    to_ward_id: str
    roster_id: str
    roster_details_id: str
    destination_roster_id: Optional[str] = None
    destination_roster_details_id: Optional[str] = None
    remarks: Optional[str] = None
    created_by: str