from api.db import db_manager
from api.models.shift import Shift
from api.types.responses import ApiResponse
from bson import ObjectId

collection = lambda: db_manager.db["shifts"]

def convert_objectid_to_str(doc):
    """Convert ObjectId fields to strings for JSON serialization"""
    if doc is None:
        return None
    if isinstance(doc, dict):
        return {k: str(v) if isinstance(v, ObjectId) else convert_objectid_to_str(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [convert_objectid_to_str(item) for item in doc]
    return doc

async def create_shift(shift: Shift) -> ApiResponse:
    try:
        result = await collection().insert_one(shift.dict())
        return ApiResponse.ok("Shift created successfully", {"id": str(result.inserted_id)})
    except Exception as e:
        return ApiResponse.fail(f"Failed to create shift: {e}")

async def get_shift(shift_id: str) -> ApiResponse:
    try:
        shift = await collection().find_one({"_id": ObjectId(shift_id)})
        if not shift:
            return ApiResponse.fail("Shift not found")
        return ApiResponse.ok("Shift retrieved successfully", convert_objectid_to_str(shift))
    except Exception as e:
        return ApiResponse.fail(f"Failed to fetch shift: {e}")

async def list_shifts() -> ApiResponse:
    try:
        shift_list = await collection().find({}).to_list(length=100)
        return ApiResponse.ok("Shifts list fetched", convert_objectid_to_str(shift_list))
    except Exception as e:
        return ApiResponse.fail(f"Failed to list shifts: {e}")

async def update_shift(shift_id: str, shift_data: dict) -> ApiResponse:
    try:
        result = await collection().update_one({"_id": ObjectId(shift_id)}, {"$set": shift_data})
        if result.modified_count == 0:
            return ApiResponse.fail("Shift not updated or not found")
        return ApiResponse.ok("Shift updated successfully", {"id": shift_id})
    except Exception as e:
        return ApiResponse.fail(f"Failed to update shift: {e}")

async def delete_shift(shift_id: str) -> ApiResponse:
    try:
        result = await collection().delete_one({"_id": ObjectId(shift_id)})
        if result.deleted_count == 0:
            return ApiResponse.fail("Shift not found")
        return ApiResponse.ok("Shift deleted successfully", {"id": shift_id})
    except Exception as e:
        return ApiResponse.fail(f"Failed to delete shift: {e}")