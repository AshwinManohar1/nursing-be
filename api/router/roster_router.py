from fastapi import APIRouter, Body, HTTPException, Query, status, Request
from typing import Optional
from api.services import roster_service
from api.models.roster import Roster
from api.types.responses import ApiResponse
from api.services.staff_service import StaffService
from api.middleware.auth import require_roles

router = APIRouter(prefix="/rosters", tags=["rosters"])

@router.post(
    "/generate",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new roster",
    description="Generate a new roster using specified method and parameters"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def generate_roster(request: Request, payload: dict) -> ApiResponse:
    roster_input = payload.get("roster_input")
    seed = payload.get("seed")
    method = payload.get("method")

    if not roster_input:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing roster_input")

    staff_details = roster_input.get("staff_details", [])
    if staff_details and isinstance(staff_details[0], str):
        staff_response = await StaffService.get_staff_by_ids(staff_details)
        print(staff_response, "staff_response")
        if not staff_response.get("success"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to fetch staff details: {staff_response.message}")
        roster_input["staff_details"] = staff_response["data"]

    # Ensure constraints exist (provide sane defaults if missing)
    roster_input.setdefault("constraints", {})
    roster_input.setdefault("shift_definitions", roster_input.get("shift_definitions", {}))
    roster_input.setdefault("meta", roster_input.get("meta", {}))

    result = await roster_service.generate_roster(roster_input, method=method, seed=seed)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)
    return result

@router.get(
    "/{roster_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get roster by ID",
    description="Retrieve a specific roster by its ID"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def get_roster(request: Request, roster_id: str) -> ApiResponse:
    """
    Get a roster by its ID.
    
    - **roster_id**: The unique identifier of the roster
    """
    if not roster_id or len(roster_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid roster ID format")
    
    result = await roster_service.get_roster(roster_id)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
    return result

@router.get(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="List all rosters",
    description="Retrieve a list of all rosters with optional filtering"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def list_rosters(
    request: Request,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of rosters to return"),
    offset: int = Query(0, ge=0, description="Number of rosters to skip")
) -> ApiResponse:
    """
    List all rosters with pagination.
    
    - **limit**: Maximum number of rosters to return (1-1000)
    - **offset**: Number of rosters to skip for pagination
    """
    result = await roster_service.list_rosters()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.message)
    return result

@router.patch(
    "/{roster_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Update roster",
    description="Update an existing roster with patches"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def update_roster(request: Request, roster_id: str, body: dict = Body(...)) -> ApiResponse:
    """
    Update an existing roster with patches.
    
    - **roster_id**: The unique identifier of the roster to update
    - **patches**: List of patches to apply to the roster
    """
    if not roster_id or len(roster_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid roster ID format")
    
    patches = body.get("patches", [])

    print(patches,"patches")
    result = await roster_service.update_roster(roster_id, patches)
    if not result.success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.message)
    return result

@router.delete(
    "/{roster_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete roster",
    description="Delete a roster by its ID"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def delete_roster(request: Request, roster_id: str) -> ApiResponse:
    """
    Delete a roster by its ID.
    
    - **roster_id**: The unique identifier of the roster to delete
    """
    if not roster_id or len(roster_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid roster ID format")
    
    result = await roster_service.delete_roster(roster_id)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
    return result

@router.get(
    "/preferences/{previous_roster_id}",
    status_code=status.HTTP_200_OK,
    summary="Compute next roster preferences from previous roster",
    description="Returns preferred day-offs based on rule: Two consecutive nights on the last two days of the previous roster implies next day OFF."
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def get_next_roster_preferences(request: Request, previous_roster_id: str):
    """
    - Input: previous_roster_id (query string)
    - Output: [
        {"id": "<emp_id>", "preferred_date_offs": ["YYYY-MM-DD"]},
        ...
      ]
    """
    if not previous_roster_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid roster ID format")
    result = await roster_service.get_next_week_preferences(previous_roster_id)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)
    return result.data
