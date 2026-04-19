from fastapi import APIRouter, HTTPException, Query, status, Request, Body
from typing import Optional
from datetime import date
from api.services.ward_transfer_service import create_ward_transfer, get_ward_transfers, cancel_ward_transfer
from api.types.responses import ApiResponse
from api.middleware.auth import require_roles

router = APIRouter(prefix="/ward-transfers", tags=["ward-transfers"])


@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a ward transfer",
    description="Transfer an employee from one ward to another for a specific date and shift"
)
@require_roles(["SUPER_ADMIN", "ADMIN"])
async def create_transfer(request: Request, payload: dict = Body(...)) -> ApiResponse:
    """
    Create a ward transfer for an employee.
    
    Required fields:
    - **staff_id**: Staff MongoDB ID (employee_id will be derived from this)
    - **hospital_id**: Hospital ID
    - **transfer_date**: Transfer date (YYYY-MM-DD)
    - **from_shift**: Shift code in source ward (M/E/N/G/ME) - must be assigned to the employee on that day
    - **to_shift**: Shift code in destination ward (M/E/N/G/ME) - will be assigned to the employee
    - **from_ward_id**: Source ward ID
    - **to_ward_id**: Destination ward ID
    - **created_by**: User ID (MongoDB ID) of the person creating the transfer
    
    Optional fields:
    - **remarks**: Optional remarks/notes for the transfer
    """
    try:
        result = await create_ward_transfer(payload)
        if not result.success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ward transfers",
    description="Retrieve a list of ward transfers with optional filtering"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def list_transfers(
    request: Request,
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    ward_id: Optional[str] = Query(None, description="Filter by ward ID (from or to)"),
    staff_id: Optional[str] = Query(None, description="Filter by staff ID"),
    transfer_date: Optional[date] = Query(None, description="Filter by specific transfer date (exact match)"),
    period_start: Optional[date] = Query(None, description="Start date for date range filter (use with period_end)"),
    period_end: Optional[date] = Query(None, description="End date for date range filter (use with period_start)"),
    status: Optional[str] = Query(None, description="Filter by status (pending/applied/cancelled). Defaults to active transfers if not specified"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of transfers to return"),
    offset: int = Query(0, ge=0, description="Number of transfers to skip")
) -> ApiResponse:
    """
    List ward transfers with optional filtering and pagination.
    
    - **hospital_id**: Filter transfers by hospital ID
    - **ward_id**: Filter transfers by ward ID (matches both source and destination)
    - **staff_id**: Filter transfers by staff ID
    - **transfer_date**: Filter transfers by specific date (exact match)
    - **period_start**: Start date for date range filter (use with period_end to get transfers within roster period)
    - **period_end**: End date for date range filter (use with period_start to get transfers within roster period)
    - **status**: Filter by transfer status (defaults to active transfers: pending/applied if not specified)
    - **limit**: Maximum number of transfers to return (1-1000)
    - **offset**: Number of transfers to skip for pagination
    """
    try:
        result = await get_ward_transfers(
            hospital_id=hospital_id,
            ward_id=ward_id,
            staff_id=staff_id,
            transfer_date=transfer_date,
            period_start=period_start,
            period_end=period_end,
            status=status,
            limit=limit,
            offset=offset
        )
        if not result.success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/{transfer_id}/cancel",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a ward transfer",
    description="Cancel a ward transfer (soft delete) and reverse its effects on active rosters"
)
@require_roles(["SUPER_ADMIN", "ADMIN"])
async def cancel_transfer(request: Request, transfer_id: str) -> ApiResponse:
    """
    Cancel a ward transfer by ID (soft delete).
    
    This will:
    - Mark transfer as cancelled (keeps record for history/audit)
    - Reverse changes to source roster (only if roster is still active - ACCEPTED/PUBLISHED)
    - Transfer record remains in database for audit trail
    
    - **transfer_id**: MongoDB ID of the transfer to cancel
    """
    try:
        result = await cancel_ward_transfer(transfer_id)
        if not result.success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

