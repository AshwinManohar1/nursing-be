from fastapi import APIRouter, HTTPException, Query, Path, status, Request
from typing import Optional
from api.models.hospital import HospitalCreate, HospitalUpdate, HospitalResponse
from api.services.hospital_service import HospitalService
from api.types.responses import ApiResponse
from api.middleware.auth import require_admin

router = APIRouter(prefix="/hospitals", tags=["hospitals"])

@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new hospital",
    description="Create a new hospital in the system"
)
@require_admin()
async def create_hospital(request: Request, hospital: HospitalCreate) -> ApiResponse:
    """
    Create a new hospital.
    
    - **name**: Name of the hospital
    - **address**: Address of the hospital
    """
    try:
        result = await HospitalService.create_hospital(hospital)
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Hospital created successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="List all hospitals",
    description="Retrieve a list of all hospitals with optional filtering and pagination"
)
@require_admin()
async def list_hospitals(
    request: Request,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    search: Optional[str] = Query(None, description="Search term for name or address")
) -> ApiResponse:
    """
    List all hospitals with optional pagination and search.
    
    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-1000)
    - **search**: Search term to filter hospitals by name or address
    """
    try:
        if search:
            result = await HospitalService.search_hospitals(search, skip, limit)
        else:
            result = await HospitalService.get_all_hospitals(skip, limit)
        
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
        return ApiResponse.ok("Hospitals retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/{hospital_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get hospital by ID",
    description="Retrieve a specific hospital by its ID"
)
@require_admin()
async def get_hospital(request: Request, hospital_id: str = Path(..., description="Hospital ID")) -> ApiResponse:
    """
    Get a hospital by its ID.
    
    - **hospital_id**: The unique identifier of the hospital
    """
    if not hospital_id or len(hospital_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid hospital ID format")
    
    try:
        result = await HospitalService.get_hospital(hospital_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Hospital retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put(
    "/{hospital_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Update hospital",
    description="Update an existing hospital"
)
@require_admin()
async def update_hospital(
    request: Request,
    hospital_id: str = Path(..., description="Hospital ID"),
    hospital: HospitalUpdate = None
) -> ApiResponse:
    """
    Update an existing hospital.
    
    - **hospital_id**: The unique identifier of the hospital to update
    - **hospital**: The hospital data to update (only provided fields will be updated)
    """
    if not hospital_id or len(hospital_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid hospital ID format")
    
    try:
        result = await HospitalService.update_hospital(hospital_id, hospital)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Hospital updated successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete(
    "/{hospital_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete hospital",
    description="Delete a hospital by its ID"
)
@require_admin()
async def delete_hospital(request: Request, hospital_id: str = Path(..., description="Hospital ID")) -> ApiResponse:
    """
    Delete a hospital by its ID.
    
    - **hospital_id**: The unique identifier of the hospital to delete
    """
    if not hospital_id or len(hospital_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid hospital ID format")
    
    try:
        result = await HospitalService.delete_hospital(hospital_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Hospital deleted successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))