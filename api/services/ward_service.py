from typing import List, Optional, Dict
from bson import ObjectId
from api.models.ward import (
    Ward,
    WardCreate,
    WardUpdate,
    WardResponse,
    get_bed_nurse_ratio_as_float
)
from api.utils.logger import get_logger

logger = get_logger("ward_service")


class WardService:
    """Service for Ward operations using Beanie"""

    @staticmethod
    async def validate_hospital_exists(hospital_id: ObjectId) -> bool:
        """Validate that the hospital exists"""
        try:
            from api.models.hospital import Hospital
            hospital = await Hospital.get(hospital_id)
            return hospital is not None
        except Exception:
            return False

    @staticmethod
    async def validate_staff_exists_and_eligible(incharge_id: ObjectId, hospital_id: ObjectId) -> bool:
        """Validate that the staff member exists and is eligible to be ward incharge"""
        try:
            from api.models.staff import Staff
            staff = await Staff.find_one({
                "_id": incharge_id,
                "hospital_id": hospital_id
            })
            if not staff:
                return False
            
            # Check if staff has appropriate grade (N4 or higher for ward incharge)
            grade = staff.grade
            if grade.startswith("N"):
                grade_num = int(grade[1:])
                return grade_num >= 4  # N4, N5, N6, N7, N8 are eligible
            return False
        except Exception:
            return False

    @staticmethod
    async def validate_ward_name_unique(name: str, hospital_id: ObjectId, exclude_ward_id: ObjectId = None) -> bool:
        """Validate that ward name is unique within the hospital"""
        try:
            query = {
                "name": name,
                "hospital_id": hospital_id
            }
            if exclude_ward_id:
                query["_id"] = {"$ne": exclude_ward_id}
            
            existing_ward = await Ward.find_one(query)
            return existing_ward is None
        except Exception:
            return False

    @staticmethod
    async def validate_bed_capacity(hospital_id: ObjectId, total_beds: int) -> bool:
        """Validate bed capacity limits (max 100 beds per ward)"""
        return 1 <= total_beds <= 100

    @staticmethod
    async def validate_ward_creation(ward: Ward) -> dict:
        """Comprehensive validation for ward creation"""
        try:
            # Validate hospital exists
            if not await WardService.validate_hospital_exists(ward.hospital_id):
                return {
                    "success": False,
                    "message": "Hospital not found",
                    "data": None
                }
            
            # Validate ward name is unique within hospital
            if not await WardService.validate_ward_name_unique(ward.name, ward.hospital_id):
                return {
                    "success": False,
                    "message": "A ward with this name already exists in this hospital",
                    "data": None
                }
            
            # Validate incharge if provided
            if ward.incharge_id:
                if not await WardService.validate_staff_exists_and_eligible(ward.incharge_id, ward.hospital_id):
                    return {
                        "success": False,
                        "message": "Invalid incharge: Staff member not found or not eligible (must be N4 or higher)",
                        "data": None
                    }
            
            # Validate bed capacity
            if not await WardService.validate_bed_capacity(ward.hospital_id, ward.total_beds):
                return {
                    "success": False,
                    "message": "Invalid bed capacity: Must be between 1 and 100 beds",
                    "data": None
                }
            
            return {
                "success": True,
                "message": "Validation passed",
                "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Validation error: {e}",
                "data": None
            }

    @staticmethod
    async def validate_ward_update(ward_id: str, ward_data: dict) -> dict:
        """Comprehensive validation for ward update"""
        try:
            # Get existing ward
            existing_ward = await Ward.get(ObjectId(ward_id))
            if not existing_ward:
                return {
                    "success": False,
                    "message": "Ward not found",
                    "data": None
                }
            
            # Validate hospital if being changed
            if "hospital_id" in ward_data:
                if not await WardService.validate_hospital_exists(ward_data["hospital_id"]):
                    return {
                        "success": False,
                        "message": "Hospital not found",
                        "data": None
                    }
            
            # Validate ward name uniqueness if being changed
            if "name" in ward_data:
                hospital_id = ward_data.get("hospital_id", existing_ward.hospital_id)
                if not await WardService.validate_ward_name_unique(ward_data["name"], hospital_id, ObjectId(ward_id)):
                    return {
                        "success": False,
                        "message": "A ward with this name already exists in this hospital",
                        "data": None
                    }
            
            # Validate incharge if being changed
            if "incharge_id" in ward_data and ward_data["incharge_id"]:
                hospital_id = ward_data.get("hospital_id", existing_ward.hospital_id)
                if not await WardService.validate_staff_exists_and_eligible(ward_data["incharge_id"], hospital_id):
                    return {
                        "success": False,
                        "message": "Invalid incharge: Staff member not found or not eligible (must be N4 or higher)",
                        "data": None
                    }
            
            # Validate bed capacity if being changed
            if "total_beds" in ward_data:
                hospital_id = ward_data.get("hospital_id", existing_ward.hospital_id)
                if not await WardService.validate_bed_capacity(hospital_id, ward_data["total_beds"]):
                    return {
                        "success": False,
                        "message": "Invalid bed capacity: Must be between 1 and 100 beds",
                        "data": None
                    }
            
            return {
                "success": True,
                "message": "Validation passed",
                "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Validation error: {e}",
                "data": None
            }

    @staticmethod
    async def create_ward(ward_data: WardCreate) -> dict:
        """Create a new ward"""
        try:
            ward = Ward(
                hospital_id=ward_data.hospital_id,
                name=ward_data.name,
                total_beds=ward_data.total_beds,
                bed_nurse_ratio=ward_data.bed_nurse_ratio,
                description=ward_data.description,
                incharge_id=ward_data.incharge_id
            )

            # Validate ward before creation
            validation_result = await WardService.validate_ward_creation(ward)
            if not validation_result["success"]:
                return validation_result

            await ward.insert()
            logger.info(f"Ward created: {ward.name}")

            return {
                "success": True,
                "message": "Ward created successfully",
                "data": WardResponse(
                    id=str(ward.id),
                    hospital_id=str(ward.hospital_id),
                    name=ward.name,
                    total_beds=ward.total_beds,
                    bed_nurse_ratio=get_bed_nurse_ratio_as_float(ward.bed_nurse_ratio),
                    description=ward.description,
                    incharge_id=str(ward.incharge_id) if ward.incharge_id else None,
                    created_at=ward.created_at,
                    updated_at=ward.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error creating ward: {e}")
            return {
                "success": False,
                "message": f"Failed to create ward: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_ward(ward_id: str) -> dict:
        """Get ward by ID"""
        try:
            if not ObjectId.is_valid(ward_id):
                return {
                    "success": False,
                    "message": "Invalid ward ID format",
                    "data": None,
                }

            ward = await Ward.get(ObjectId(ward_id))
            if not ward:
                return {"success": False, "message": "Ward not found", "data": None}

            return {
                "success": True,
                "message": "Ward retrieved successfully",
                "data": WardResponse(
                    id=str(ward.id),
                    hospital_id=str(ward.hospital_id),
                    name=ward.name,
                    total_beds=ward.total_beds,
                    bed_nurse_ratio=get_bed_nurse_ratio_as_float(ward.bed_nurse_ratio),
                    description=ward.description,
                    incharge_id=str(ward.incharge_id) if ward.incharge_id else None,
                    created_at=ward.created_at,
                    updated_at=ward.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error getting ward: {e}")
            return {
                "success": False,
                "message": f"Failed to get ward: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_all_wards(skip: int = 0, limit: int = 100, hospital_id: Optional[str] = None, incharge_id: Optional[str] = None) -> dict:
        """Get all wards with pagination and filtering"""
        try:
            # Build filter query
            filter_query = {}
            if hospital_id:
                if not ObjectId.is_valid(hospital_id):
                    return {
                        "success": False,
                        "message": "Invalid hospital_id format",
                        "data": None,
                    }
                filter_query["hospital_id"] = ObjectId(hospital_id)
            
            if incharge_id:
                if not ObjectId.is_valid(incharge_id):
                    return {
                        "success": False,
                        "message": "Invalid incharge_id format",
                        "data": None,
                    }
                filter_query["incharge_id"] = ObjectId(incharge_id)

            # Execute query with pagination
            ward_list = await Ward.find(filter_query).skip(skip).limit(limit).to_list()
            
            # Get total count for pagination info
            total_count = await Ward.find(filter_query).count()

            ward_responses = [
                WardResponse(
                    id=str(ward.id),
                    hospital_id=str(ward.hospital_id),
                    name=ward.name,
                    total_beds=ward.total_beds,
                    bed_nurse_ratio=get_bed_nurse_ratio_as_float(ward.bed_nurse_ratio),
                    description=ward.description,
                    incharge_id=str(ward.incharge_id) if ward.incharge_id else None,
                    created_at=ward.created_at,
                    updated_at=ward.updated_at,
                )
                for ward in ward_list
            ]

            return {
                "success": True,
                "message": f"Retrieved {len(ward_responses)} wards",
                "data": {
                    "wards": ward_responses,
                    "pagination": {
                        "total": total_count,
                        "limit": limit,
                        "offset": skip,
                        "has_more": skip + limit < total_count
                    }
                },
            }
        except Exception as e:
            logger.error(f"Error getting wards: {e}")
            return {
                "success": False,
                "message": f"Failed to get wards: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def update_ward(ward_id: str, ward_data: WardUpdate) -> dict:
        """Update ward by ID"""
        try:
            if not ObjectId.is_valid(ward_id):
                return {
                    "success": False,
                    "message": "Invalid ward ID format",
                    "data": None,
                }

            ward = await Ward.get(ObjectId(ward_id))
            if not ward:
                return {"success": False, "message": "Ward not found", "data": None}

            # Convert WardUpdate to dict for validation
            update_dict = ward_data.dict(exclude_unset=True)
            
            # Validate ward update
            validation_result = await WardService.validate_ward_update(ward_id, update_dict)
            if not validation_result["success"]:
                return validation_result

            # Update fields if provided
            if update_dict:
                for field, value in update_dict.items():
                    setattr(ward, field, value)

                ward.update_timestamp()
                await ward.save()

            return {
                "success": True,
                "message": "Ward updated successfully",
                "data": WardResponse(
                    id=str(ward.id),
                    hospital_id=str(ward.hospital_id),
                    name=ward.name,
                    total_beds=ward.total_beds,
                    bed_nurse_ratio=get_bed_nurse_ratio_as_float(ward.bed_nurse_ratio),
                    description=ward.description,
                    incharge_id=str(ward.incharge_id) if ward.incharge_id else None,
                    created_at=ward.created_at,
                    updated_at=ward.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error updating ward: {e}")
            return {
                "success": False,
                "message": f"Failed to update ward: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def validate_ward_deletion(ward_id: str) -> dict:
        """Validate that ward can be safely deleted"""
        try:
            # Check if any staff are assigned to this ward
            from api.models.staff import Staff
            staff_assigned = await Staff.find_one({"ward_id": ObjectId(ward_id)})
            if staff_assigned:
                return {
                    "success": False,
                    "message": "Cannot delete ward: Staff members are still assigned to this ward",
                    "data": None
                }
            
            # Check if ward has any active rosters or schedules
            # This would require checking roster/schedule collections if they exist
            # For now, we'll allow deletion if no staff are assigned
            
            return {
                "success": True,
                "message": "Ward can be safely deleted",
                "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Validation error: {e}",
                "data": None
            }

    @staticmethod
    async def delete_ward(ward_id: str) -> dict:
        """Delete ward by ID"""
        try:
            if not ObjectId.is_valid(ward_id):
                return {
                    "success": False,
                    "message": "Invalid ward ID format",
                    "data": None,
                }

            ward = await Ward.get(ObjectId(ward_id))
            if not ward:
                return {"success": False, "message": "Ward not found", "data": None}

            # Validate ward can be deleted
            validation_result = await WardService.validate_ward_deletion(ward_id)
            if not validation_result["success"]:
                return validation_result

            await ward.delete()
            logger.info(f"Ward deleted: {ward.name}")

            return {
                "success": True,
                "message": "Ward deleted successfully",
                "data": None,
            }
        except Exception as e:
            logger.error(f"Error deleting ward: {e}")
            return {
                "success": False,
                "message": f"Failed to delete ward: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_wards_by_hospital(hospital_id: str, ward_name: Optional[str] = None) -> dict:
        """Get wards by hospital with optional ward name filter"""
        try:
            if not ObjectId.is_valid(hospital_id):
                return {
                    "success": False,
                    "message": "Invalid hospital ID format",
                    "data": None,
                }

            filter_dict = {"hospital_id": ObjectId(hospital_id)}
            if ward_name:
                filter_dict["name"] = ward_name
            
            wards = await Ward.find(filter_dict).to_list()
            
            ward_responses = [
                WardResponse(
                    id=str(ward.id),
                    hospital_id=str(ward.hospital_id),
                    name=ward.name,
                    total_beds=ward.total_beds,
                    bed_nurse_ratio=get_bed_nurse_ratio_as_float(ward.bed_nurse_ratio),
                    description=ward.description,
                    incharge_id=str(ward.incharge_id) if ward.incharge_id else None,
                    created_at=ward.created_at,
                    updated_at=ward.updated_at,
                )
                for ward in wards
            ]

            return {
                "success": True,
                "message": f"Retrieved {len(ward_responses)} wards for hospital",
                "data": ward_responses,
            }
        except Exception as e:
            logger.error(f"Error getting wards by hospital: {e}")
            return {
                "success": False,
                "message": f"Failed to get wards by hospital: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_ward_bed_nurse_ratio(ward_id: str) -> dict:
        """Get bed to nurse ratio as string"""
        try:
            if not ObjectId.is_valid(ward_id):
                return {
                    "success": False,
                    "message": "Invalid ward ID format",
                    "data": None,
                }

            ward = await Ward.get(ObjectId(ward_id))
            if not ward:
                return {"success": False, "message": "Ward not found", "data": None}

            return {
                "success": True,
                "message": "Ward bed-nurse ratio retrieved successfully",
                "data": {
                    "ward_id": str(ward.id),
                    "ward_name": ward.name,
                    "bed_nurse_ratio": ward.bed_nurse_ratio,
                    "ratio_as_float": get_bed_nurse_ratio_as_float(ward.bed_nurse_ratio)
                },
            }
        except Exception as e:
            logger.error(f"Error getting ward bed-nurse ratio: {e}")
            return {
                "success": False,
                "message": f"Failed to get ward bed-nurse ratio: {str(e)}",
                "data": None,
            }