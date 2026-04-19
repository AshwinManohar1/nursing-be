from fastapi import APIRouter, HTTPException, Query, status, Request
from typing import Optional, List
from api.services.ward_service import WardService
from api.models.ward import (
    WardCreate, WardUpdate, WardResponse,
    convert_hospital_id, convert_incharge_id, validate_bed_nurse_ratio
)
from api.types.responses import ApiResponse
from api.middleware.auth import require_admin, require_roles

router = APIRouter(prefix="/wards", tags=["wards"])

@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ward",
    description="Create a new ward in the hospital system"
)
@require_admin()
async def create_ward(request: Request, ward_input: dict) -> ApiResponse:
    """
    Create a new ward.
    
    - **hospital_id**: ID of the hospital this ward belongs to
    - **name**: Name of the ward
    - **total_beds**: Total number of beds in the ward
    - **bed_nurse_ratio**: Bed to nurse ratio in format 'beds:nurses'
    - **description**: Description of the ward
    - **incharge_id**: ID of the staff member in charge (optional)
    """
    try:
        # Convert input data to proper types
        ward_data = WardCreate(
            hospital_id=convert_hospital_id(ward_input["hospital_id"]),
            name=ward_input["name"],
            total_beds=ward_input["total_beds"],
            bed_nurse_ratio=validate_bed_nurse_ratio(ward_input["bed_nurse_ratio"]),
            description=ward_input["description"],
            incharge_id=convert_incharge_id(ward_input.get("incharge_id"))
        )
        
        result = await WardService.create_ward(ward_data)
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Ward created successfully", result.get("data"))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/{ward_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ward by ID",
    description="Retrieve a specific ward by its ID"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def get_ward(request: Request, ward_id: str) -> ApiResponse:
    """
    Get a ward by its ID.
    
    - **ward_id**: The unique identifier of the ward
    """
    if not ward_id or len(ward_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ward ID format")
    
    try:
        result = await WardService.get_ward(ward_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Ward retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="List all wards",
    description="Retrieve a list of all wards with optional filtering"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def list_wards(
    request: Request,
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    incharge_id: Optional[str] = Query(None, description="Filter by incharge ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of wards to return"),
    offset: int = Query(0, ge=0, description="Number of wards to skip")
) -> ApiResponse:
    """
    List all wards with optional filtering and pagination.
    
    - **hospital_id**: Filter wards by hospital ID
    - **incharge_id**: Filter wards by incharge ID
    - **limit**: Maximum number of wards to return (1-1000)
    - **offset**: Number of wards to skip for pagination
    """
    try:
        result = await WardService.get_all_wards(offset, limit, hospital_id, incharge_id)
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
        return ApiResponse.ok("Wards retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put(
    "/{ward_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Update ward",
    description="Update an existing ward"
)
@require_admin()
async def update_ward(request: Request, ward_id: str, ward_update: dict) -> ApiResponse:
    """
    Update an existing ward.
    
    - **ward_id**: The unique identifier of the ward to update
    - **ward_update**: The ward data to update (only provided fields will be updated)
    """
    if not ward_id or len(ward_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ward ID format")
    
    try:
        # Convert input data to proper types
        ward_data = {}
        if "hospital_id" in ward_update and ward_update["hospital_id"] is not None:
            ward_data["hospital_id"] = convert_hospital_id(ward_update["hospital_id"])
        if "name" in ward_update and ward_update["name"] is not None:
            ward_data["name"] = ward_update["name"]
        if "total_beds" in ward_update and ward_update["total_beds"] is not None:
            ward_data["total_beds"] = ward_update["total_beds"]
        if "bed_nurse_ratio" in ward_update and ward_update["bed_nurse_ratio"] is not None:
            ward_data["bed_nurse_ratio"] = validate_bed_nurse_ratio(ward_update["bed_nurse_ratio"])
        if "description" in ward_update and ward_update["description"] is not None:
            ward_data["description"] = ward_update["description"]
        if "incharge_id" in ward_update and ward_update["incharge_id"] is not None:
            ward_data["incharge_id"] = convert_incharge_id(ward_update["incharge_id"])
        
        if not ward_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")
        
        # Create WardUpdate object
        ward_update_obj = WardUpdate(**ward_data)
        
        result = await WardService.update_ward(ward_id, ward_update_obj)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Ward updated successfully", result.get("data"))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete(
    "/{ward_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete ward",
    description="Delete a ward by its ID"
)
@require_admin()
async def delete_ward(request: Request, ward_id: str) -> ApiResponse:
    """
    Delete a ward by its ID.
    
    - **ward_id**: The unique identifier of the ward to delete
    """
    if not ward_id or len(ward_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ward ID format")
    
    try:
        result = await WardService.delete_ward(ward_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Ward deleted successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/hospital/{hospital_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get wards by hospital",
    description="Retrieve all wards for a specific hospital"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def get_wards_by_hospital(
    request: Request,
    hospital_id: str,
    ward_name: Optional[str] = Query(None, description="Filter by ward name")
) -> ApiResponse:
    """
    Get all wards for a specific hospital.
    
    - **hospital_id**: The unique identifier of the hospital
    - **ward_name**: Optional ward name filter
    """
    if not hospital_id or len(hospital_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid hospital ID format")
    
    try:
        result = await WardService.get_wards_by_hospital(hospital_id, ward_name)
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
        return ApiResponse.ok("Hospital wards retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/{ward_id}/ratio",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ward bed-nurse ratio",
    description="Get the bed to nurse ratio for a specific ward"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def get_ward_bed_nurse_ratio(request: Request, ward_id: str) -> ApiResponse:
    """
    Get the bed to nurse ratio for a specific ward.
    
    - **ward_id**: The unique identifier of the ward
    """
    if not ward_id or len(ward_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ward ID format")
    
    try:
        result = await WardService.get_ward_bed_nurse_ratio(ward_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Ward bed-nurse ratio retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))