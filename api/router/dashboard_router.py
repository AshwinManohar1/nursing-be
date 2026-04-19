from fastapi import APIRouter, Request
from api.types.responses import WardPerformanceResponse, KPISummary, WardPerformanceItem, AISuggestion
from api.middleware.auth import require_admin
from datetime import date

router = APIRouter()

@router.get("/ward-performance", response_model=WardPerformanceResponse)
@require_admin()
async def get_ward_performance(request: Request, current_user: dict = None):
    return WardPerformanceResponse(
        hospital_id="demo-hospital-001",
        date=date.today(),
        shift="M",
        kpis=KPISummary(
            total_patients=142,
            bed_occupancy_percentage=78.5,
            live_rosters="12/15",
            active_wards=8,
            occupancy_status="Normal Occupancy"
        ),
        ward_performance=[
            WardPerformanceItem(
                ward_id="ward-001",
                ward_name="ICU",
                shift_patients="18",
                shift_nurses="6",
                ideal_ratio="3.0",
                occupancy="high",
                nurse_utilization="High",
                deficit_surplus="-1",
                beds_available="2",
                transfers_in=2,
                transfers_out=1,
                total_transfers=3
            ),
            WardPerformanceItem(
                ward_id="ward-002",
                ward_name="General Ward A",
                shift_patients="32",
                shift_nurses="8",
                ideal_ratio="5.0",
                occupancy="medium",
                nurse_utilization="Medium",
                deficit_surplus="+2",
                beds_available="8",
                transfers_in=1,
                transfers_out=3,
                total_transfers=4
            ),
            WardPerformanceItem(
                ward_id="ward-003",
                ward_name="Pediatrics",
                shift_patients="21",
                shift_nurses="7",
                ideal_ratio="4.0",
                occupancy="medium",
                nurse_utilization="Medium",
                deficit_surplus="0",
                beds_available="9",
                transfers_in=0,
                transfers_out=1,
                total_transfers=1
            ),
            WardPerformanceItem(
                ward_id="ward-004",
                ward_name="Emergency",
                shift_patients="15",
                shift_nurses="5",
                ideal_ratio="3.0",
                occupancy="low",
                nurse_utilization="Low",
                deficit_surplus="+1",
                beds_available="5",
                transfers_in=4,
                transfers_out=2,
                total_transfers=6
            ),
        ],
        ai_suggestions=[
            AISuggestion(
                type="staffing",
                title="ICU understaffed on morning shift",
                message="ICU has 18 patients but only 6 nurses. Consider reassigning 1 nurse from General Ward A.",
                priority="high"
            ),
            AISuggestion(
                type="occupancy",
                title="General Ward A approaching capacity",
                message="General Ward A is at 80% occupancy. Plan for potential overflow.",
                priority="medium"
            ),
        ]
    )
