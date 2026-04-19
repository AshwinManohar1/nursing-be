from fastapi import APIRouter, Query, Request
from api.services.dashboard_service import DashboardService
from api.types.responses import WardPerformanceResponse, KPISummaryResponse
from api.middleware.auth import require_admin
from datetime import date, datetime
from typing import Optional

router = APIRouter()

@router.get("/ward-performance", response_model=WardPerformanceResponse)
@require_admin()
async def get_ward_performance(
    request: Request,
    hospital_id: str = Query(..., description="Hospital ID"),
    date: Optional[date] = Query(None, description="Date (defaults to today)"),
    shift: Optional[str] = Query(None, description="Shift: M, E, N"),
    ward_name: Optional[str] = Query(None, description="Specific ward name")
):
    if not date:
        date = datetime.now().date()
    
    return await DashboardService.get_ward_performance(hospital_id, date, shift, ward_name)