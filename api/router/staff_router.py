from fastapi import APIRouter, UploadFile, File, HTTPException, Query, status, Form, Request, Body
from typing import Optional
from api.services.staff_service import StaffService
from api.models.staff import StaffCreate, StaffUpdate
from api.types.responses import ApiResponse
from api.middleware.auth import require_admin, require_roles
from api.utils.logger import get_logger
from bson import ObjectId

logger = get_logger("staff_router")

router = APIRouter(prefix="/staff", tags=["staff"])

@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new staff member",
    description="Create a new staff member in the system"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def create_staff(request: Request, current_user: Optional[dict] = None) -> ApiResponse:
    """
    Create a new staff member.
    
    - **name**: Name of the staff member
    - **email**: Email address of the staff member
    - **contact_no**: Contact number of the staff member
    - **emp_id**: Employee ID
    - **grade**: Staff grade (N1-N8)
    - **position**: Position of the staff member
    - **hospital_id**: ID of the hospital
    - **ward_id**: List of ward IDs (required for WARD_INCHARGE, must be one of their managed wards)
    
    Note:
    - WARD_INCHARGE can only create staff for wards they manage
    - WARD_INCHARGE must provide ward_id (cannot be empty)
    """
    try:
        # Parse JSON body directly
        body = await request.json()
        try:
            staff = StaffCreate(**body)
        except Exception as validation_error:
            # Better error message for validation errors
            error_msg = str(validation_error)
            if "validation error" in error_msg.lower():
                # Extract the actual validation error message
                import re
                match = re.search(r'Value error, (.+?)(?:\n|\[)', error_msg)
                if match:
                    error_msg = match.group(1)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Validation error: {error_msg}"
            )
        
        result = await StaffService.create_staff(staff, current_user)
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Staff created successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_staff endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/{staff_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get staff member by ID",
    description="Retrieve a specific staff member by their ID"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def get_staff(request: Request, staff_id: str) -> ApiResponse:
    """
    Get a staff member by their ID.
    
    - **staff_id**: The unique identifier of the staff member
    """
    if not staff_id or len(staff_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid staff ID format")
    
    try:
        result = await StaffService.get_staff(staff_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Staff retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="List all staff members",
    description="Retrieve a list of all staff members with optional filtering"
)
@require_roles(["SUPER_ADMIN", "ADMIN", "WARD_INCHARGE"])
async def list_staff(
    request: Request,
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    ward_id: Optional[str] = Query(None, description="Filter by ward ID"),
    grade: Optional[str] = Query(None, description="Filter by staff grade"),
    search: Optional[str] = Query(None, description="Search term to filter by name, email, or employee ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of staff to return"),
    offset: Optional[int] = Query(None, ge=0, description="Number of staff to skip (alternative to page)"),
    page: Optional[int] = Query(None, ge=1, description="Page number (1-indexed, alternative to offset)"),
    current_user: Optional[dict] = None
) -> ApiResponse:
    """
    List all staff members with optional filtering and pagination.
    
    Returns a paginated response with:
    - **items**: List of staff members
    - **pagination**: Pagination metadata (total, limit, offset, current_page, total_pages, has_next, has_prev)
    
    Query Parameters:
    - **hospital_id**: Filter staff by hospital ID
    - **ward_id**: Filter staff by ward ID
    - **grade**: Filter staff by grade (N1-N8)
    - **search**: Search term to filter by name, email, or employee ID (case-insensitive)
    - **limit**: Maximum number of staff to return (1-1000)
    - **offset**: Number of staff to skip for pagination (alternative to page)
    - **page**: Page number (1-indexed, alternative to offset). If both provided, page takes precedence.
    """
    try:
        # Calculate offset from page if page is provided, otherwise use offset
        calculated_offset = offset
        if page is not None:
            calculated_offset = (page - 1) * limit
        elif offset is None:
            calculated_offset = 0

        # Apply role-based filtering
        user_role = current_user.get("role") if current_user else None
        filtered_hospital_id = hospital_id
        filtered_ward_id = ward_id
        ward_ids_list = None

        if user_role == "WARD_INCHARGE":
            # WARD_INCHARGE can only see staff from their assigned wards
            staff_id = current_user.get("staff_id")
            if not staff_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Unable to verify ward access: staff_id not found"
                )
            
            from api.models.staff import Staff
            incharge_staff = await Staff.get(ObjectId(staff_id))
            if not incharge_staff or not incharge_staff.ward_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not assigned to any wards"
                )
            
            ward_ids_list = [str(w_id) for w_id in incharge_staff.ward_id]
            filtered_hospital_id = str(incharge_staff.hospital_id)
            filtered_ward_id = None
            
        elif user_role == "ADMIN":
            # ADMIN can only see staff from their hospital
            org_id = current_user.get("org_id")
            if org_id:
                filtered_hospital_id = org_id
            else:
                # Fallback: get from staff record
                staff_id = current_user.get("staff_id")
                if staff_id:
                    from api.models.staff import Staff
                    admin_staff = await Staff.get(ObjectId(staff_id))
                    if admin_staff:
                        filtered_hospital_id = str(admin_staff.hospital_id)
        
        # SUPER_ADMIN: No filtering needed
        
        result = await StaffService.get_all_staff(
            calculated_offset, 
            limit, 
            filtered_hospital_id, 
            filtered_ward_id, 
            grade, 
            search,
            ward_ids=ward_ids_list
        )
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
        return ApiResponse.ok("Staff list retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put(
    "/{staff_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Update staff member",
    description="Update an existing staff member"
)
@require_admin()
async def update_staff(request: Request, staff_id: str, staff_update: StaffUpdate) -> ApiResponse:
    """
    Update an existing staff member.    
    
    - **staff_id**: The unique identifier of the staff member to update
    - **staff_update**: The staff data to update (only provided fields will be updated)
    """
    if not staff_id or len(staff_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid staff ID format")
    
    try:
        result = await StaffService.update_staff(staff_id, staff_update)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Staff updated successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete(
    "/{staff_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete staff member",
    description="Delete a staff member by their ID"
)
@require_admin()
async def delete_staff(request: Request, staff_id: str) -> ApiResponse:
    """
    Delete a staff member by their ID.
    
    - **staff_id**: The unique identifier of the staff member to delete
    """
    if not staff_id or len(staff_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid staff ID format")
    
    try:
        result = await StaffService.delete_staff(staff_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Staff deleted successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post(
    "/upload",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload staff data file",
    description="Upload a file containing staff data for bulk import"
)
@require_admin()
async def upload_staff_file(
    request: Request,
    file: UploadFile = File(...),
    hospital_id: str = Form(..., description="Hospital ID to assign for all uploaded staff")
) -> ApiResponse:
    """
    Upload a file containing staff data for bulk import.
    
    - **file**: The file containing staff data (CSV, Excel, etc.)
    """
    try:
        result = await StaffService.upload_staff_file(file, hospital_id)
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("Staff file uploaded successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))