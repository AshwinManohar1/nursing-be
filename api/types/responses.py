from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from datetime import datetime, date

class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Any | Dict
    timestamp: str

    @classmethod
    def ok(cls, message: str, data: Any):
        return cls(success=True, message=message, data=data, timestamp=datetime.utcnow().isoformat())

    @classmethod
    def fail(cls, message: str):
        return cls(success=False, message=message, data={}, timestamp=datetime.utcnow().isoformat())

# Dashboard Response Types
class WardPerformanceItem(BaseModel):
    ward_id: str
    ward_name: str
    shift_patients: str  # e.g., "17", "-" (for no data)
    shift_nurses: str  # e.g., "7", "-" (for no nurses)
    ideal_ratio: str  # e.g., "5:1", "3:1"
    occupancy: str  # e.g., "70%", "85%"
    nurse_utilization: str  # e.g., "High", "Medium", "Low", "N/A"
    deficit_surplus: str  # e.g., "+1", "-2", "0", "N/A"
    beds_available: str
    transfers_in: int = 0  # Incoming transfers within roster period
    transfers_out: int = 0  # Outgoing transfers within roster period
    total_transfers: int = 0  # Total transfers (in + out)

class KPISummary(BaseModel):
    total_patients: int
    bed_occupancy_percentage: float
    live_rosters: str  # "15/18" format
    active_wards: int  # Number of wards with accepted rosters
    occupancy_status: str

class AISuggestion(BaseModel):
    type: str
    title: str
    message: str
    priority: str  # "high", "medium", "low"

class WardPerformanceResponse(BaseModel):
    hospital_id: str
    date: date
    shift: Optional[str]
    kpis: KPISummary
    ward_performance: List[WardPerformanceItem]
    ai_suggestions: List[AISuggestion]

class KPISummaryResponse(BaseModel):
    hospital_id: str
    date: date
    kpis: KPISummary