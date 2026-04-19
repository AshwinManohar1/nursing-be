from fastapi import APIRouter, Query, HTTPException, status, Request
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
from api.services.ward_occupancy_service import WardOccupancyService
from api.models.ward_occupancy import WardOccupancyResponse
from api.types.responses import ApiResponse
from api.middleware.auth import require_admin

router = APIRouter(prefix="/ward-occupancy", tags=["ward-occupancy"])

class EmailBodyRequest(BaseModel):
    email_body: str


@router.post("/parse-email", response_model=ApiResponse)
async def parse_email_and_save(request: EmailBodyRequest):
    """
    Parse HTML email body containing ward occupancy data and save to database
    """
    try:
        # Parse the email HTML
        parse_result = WardOccupancyService.parse_email_html(request.email_body)
        
        if not parse_result["success"]:
            return ApiResponse.fail(parse_result["message"])
        
        # Save the parsed data
        save_result = await WardOccupancyService.save_ward_occupancy_data(parse_result["data"])
        
        if not save_result.success:
            return save_result
        
        return save_result
        
    except Exception as e:
        return ApiResponse.fail(f"Internal server error: {str(e)}")


@router.get("/", response_model=ApiResponse)
@require_admin()
async def get_ward_occupancy_data(
    request: Request,
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    ward_name: Optional[str] = Query(None, description="Filter by ward name"),
    report_date: Optional[date] = Query(None, description="Filter by report date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip")
):
    """
    Get ward occupancy data with optional filters
    """
    try:
        # Get data from service
        result = await WardOccupancyService.get_ward_occupancy_data(
            hospital_id=hospital_id,
            ward_name=ward_name,
            report_date=report_date,
            limit=limit,
            offset=offset
        )
        
        return result
        
    except Exception as e:
        return ApiResponse.fail(f"Internal server error: {str(e)}")


@router.get("/{occupancy_id}", response_model=ApiResponse)
@require_admin()
async def get_ward_occupancy_by_id(request: Request, occupancy_id: str):
    """
    Get a single ward occupancy record by ID
    """
    try:
        result = await WardOccupancyService.get_ward_occupancy_by_id(occupancy_id)
        return result
    except Exception as e:
        return ApiResponse.fail(f"Internal server error: {str(e)}")


@router.get(
    "/list/all", 
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="List all ward occupancy records",
    description="Retrieve all ward occupancy records with pagination"
)
@require_admin()
async def list_all_ward_occupancy_records(request: Request, limit: int = Query(100, ge=1, le=1000)) -> ApiResponse:
    """
    List all ward occupancy records with pagination.
    
    - **limit**: Maximum number of records to return (1-1000)
    """
    try:
        result = await WardOccupancyService.list_ward_occupancy_records(limit)
        return result
    except Exception as e:
        return ApiResponse.fail(f"Internal server error: {str(e)}")


@router.put(
    "/{occupancy_id}", 
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Update ward occupancy record",
    description="Update an existing ward occupancy record"
)
@require_admin()
async def update_ward_occupancy(request: Request, occupancy_id: str, update_data: dict) -> ApiResponse:
    """
    Update a ward occupancy record.
    
    - **occupancy_id**: The unique identifier of the occupancy record
    - **update_data**: The data to update
    """
    if not occupancy_id or len(occupancy_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid occupancy ID format")
    
    try:
        result = await WardOccupancyService.update_ward_occupancy(occupancy_id, update_data)
        if not result.success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        return ApiResponse.fail(f"Internal server error: {str(e)}")


@router.delete(
    "/{occupancy_id}", 
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete ward occupancy record",
    description="Delete a ward occupancy record by its ID"
)
@require_admin()
async def delete_ward_occupancy(request: Request, occupancy_id: str) -> ApiResponse:
    """
    Delete a ward occupancy record.
    
    - **occupancy_id**: The unique identifier of the occupancy record to delete
    """
    if not occupancy_id or len(occupancy_id) != 24:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid occupancy ID format")
    
    try:
        result = await WardOccupancyService.delete_ward_occupancy(occupancy_id)
        if not result.success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        return ApiResponse.fail(f"Internal server error: {str(e)}")


@router.post("/create", response_model=ApiResponse)
async def create_ward_occupancy(occupancy_data: dict):
    """
    Create a single ward occupancy record directly
    """
    try:
        from api.models.ward_occupancy import WardOccupancyCreate
        
        # Create WardOccupancyCreate object
        occupancy_create = WardOccupancyCreate(**occupancy_data)
        
        # Save to database
        result = await WardOccupancyService.save_ward_occupancy_data([occupancy_create])
        
        return result
        
    except Exception as e:
        return ApiResponse.fail(f"Failed to create occupancy record: {str(e)}")

