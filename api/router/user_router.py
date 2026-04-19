from fastapi import APIRouter, HTTPException, Query, status, Request, Body
from typing import Optional
from api.config import SUPER_ADMIN_SECRET_KEY
from api.services.user_service import UserService
from api.models.user import UserCreate, UserUpdate
from api.types.responses import ApiResponse
from api.middleware.auth import require_super_admin_or_secret
from bson import ObjectId

router = APIRouter(prefix="/api/v1/users", tags=["Users"])

@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Create a new user account with access credentials"
)
@require_super_admin_or_secret()
async def create_user(request: Request, current_user: Optional[dict] = None) -> ApiResponse:
    """
    Create a new user account.
    
    - **employee_id**: Employee ID for login (required, must be unique)
    - **password**: Password (minimum 8 characters)
    - **role**: User role - SUPER_ADMIN, ADMIN, WARD_INCHARGE, or STAFF
    - **staff_id**: Staff ID (required for ADMIN, WARD_INCHARGE, and STAFF; optional only for SUPER_ADMIN)
    
    Note:
    - For WARD_INCHARGE role, the staff must have position 'ward-incharge'
    - For ADMIN, WARD_INCHARGE, and STAFF roles, staff_id is required
    - The employee_id must match the staff.emp_id if staff_id is provided
    """

    try:
        # Parse JSON body directly
        body = await request.json()
        user_data = UserCreate(**body)
        result = await UserService.create_user(user_data)
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("User created successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/{user_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user by ID",
    description="Retrieve a specific user by their ID"
)
@require_super_admin_or_secret()
async def get_user(request: Request, user_id: str, current_user: Optional[dict] = None) -> ApiResponse:
    """
    Get a user by their ID.
    
    - **user_id**: The unique identifier of the user
    """
    
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    try:
        result = await UserService.get_user(user_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("User retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="List all users",
    description="Retrieve a list of all users with optional filtering"
)
@require_super_admin_or_secret()
async def list_users(
    request: Request,
    role: Optional[str] = Query(None, description="Filter by role (SUPER_ADMIN, ADMIN, WARD_INCHARGE, STAFF)"),
    status: Optional[str] = Query(None, description="Filter by status (PENDING, ACTIVE, SUSPENDED, LOCKED)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    current_user: Optional[dict] = None
) -> ApiResponse:
    """
    List all users with optional filtering and pagination.
    
    - **role**: Filter users by role
    - **status**: Filter users by status
    - **limit**: Maximum number of users to return (1-1000)
    - **offset**: Number of users to skip for pagination
    """
    
    try:
        result = await UserService.get_all_users(offset, limit, role, status)
        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["message"])
        return ApiResponse.ok("Users list retrieved successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put(
    "/{user_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user",
    description="Update an existing user"
)
@require_super_admin_or_secret()
async def update_user(
    request: Request,
    user_id: str,
    current_user: Optional[dict] = None
) -> ApiResponse:
    """
    Update an existing user.
    
    - **user_id**: The unique identifier of the user to update
    - **user_update**: The user data to update (only provided fields will be updated)
    """
    
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    try:
        # Parse JSON body directly
        body = await request.json()
        user_update = UserUpdate(**body)
        result = await UserService.update_user(user_id, user_update)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("User updated successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete(
    "/{user_id}",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete user",
    description="Delete a user by their ID"
)
@require_super_admin_or_secret()
async def delete_user(
    request: Request,
    user_id: str,
    current_user: Optional[dict] = None
) -> ApiResponse:
    """
    Delete a user by their ID.
    
    - **user_id**: The unique identifier of the user to delete
    """
    
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    try:
        result = await UserService.delete_user(user_id)
        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        return ApiResponse.ok("User deleted successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

