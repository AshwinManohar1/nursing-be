from fastapi import APIRouter, HTTPException, Query, status, Request
from typing import Optional
from api.services import shift_service
from api.models.shift import Shift, ShiftCreate, ShiftUpdate
from api.types.responses import ApiResponse
from api.middleware.auth import require_admin

router = APIRouter(prefix="/shifts", tags=["shifts"])

@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new shift",
    description="Create a new shift definition in the system"
)
@require_admin()
async def create_shift(request: Request, shift: ShiftCreate) -> ApiResponse:
    """
    Create a new shift definition.
    
    - **name**: Name of the shift
    - **start_time**: Start time of the shift
    - **end_time**: End time of the shift
    - **description**: Description of the shift
    """
    try:
        # Convert ShiftCreate to Shift model
        shift_data = {
            "code": shift.name[:1].upper(),  # Use first letter of name as code
            "name": shift.name,
            "hours": 8,  # Default hours
            "start_time": shift.start_time.isoformat(),
            "end_time": shift.end_time.isoformat(),
            "break_minutes": 30  # Default break
        }
        shift_model = Shift(**shift_data)
        
        result = await shift_service.create_shift(shift_model)
        if not result.success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/{shift_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get shift by ID",
    description="Retrieve a specific shift by its ID"
)
@require_admin()
async def get_shift(request: Request, shift_id: str) -> ApiResponse:
    """
    Get a shift by its ID.
    
    - **shift_id**: The unique identifier of the shift
    """
    if not shift_id or len(shift_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid shift ID format")
    
    try:
        result = await shift_service.get_shift(shift_id)
        if not result.success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="List all shifts",
    description="Retrieve a list of all shift definitions"
)
@require_admin()
async def list_shifts(
    request: Request,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of shifts to return"),
    offset: int = Query(0, ge=0, description="Number of shifts to skip")
) -> ApiResponse:
    """
    List all shift definitions with pagination.
    
    - **limit**: Maximum number of shifts to return (1-1000)
    - **offset**: Number of shifts to skip for pagination
    """
    try:
        return await shift_service.list_shifts()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put(
    "/{shift_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Update shift",
    description="Update an existing shift definition"
)
@require_admin()
async def update_shift(request: Request, shift_id: str, shift_update: ShiftUpdate) -> ApiResponse:
    """
    Update an existing shift definition.
    
    - **shift_id**: The unique identifier of the shift to update
    - **shift_update**: The shift data to update (only provided fields will be updated)
    """
    if not shift_id or len(shift_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid shift ID format")
    
    try:
        # Convert ShiftUpdate to dict
        shift_data = {}
        if shift_update.name is not None:
            shift_data["name"] = shift_update.name
            shift_data["code"] = shift_update.name[:1].upper()
        if shift_update.start_time is not None:
            shift_data["start_time"] = shift_update.start_time.isoformat()
        if shift_update.end_time is not None:
            shift_data["end_time"] = shift_update.end_time.isoformat()
        
        if not shift_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")
        
        result = await shift_service.update_shift(shift_id, shift_data)
        if not result.success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete(
    "/{shift_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete shift",
    description="Delete a shift definition by its ID"
)
@require_admin()
async def delete_shift(request: Request, shift_id: str) -> ApiResponse:
    """
    Delete a shift definition by its ID.
    
    - **shift_id**: The unique identifier of the shift to delete
    """
    if not shift_id or len(shift_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid shift ID format")
    
    try:
        result = await shift_service.delete_shift(shift_id)
        if not result.success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))