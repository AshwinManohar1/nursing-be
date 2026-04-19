from typing import List, Optional
from bson import ObjectId
from api.models.hospital import (
    Hospital,
    HospitalCreate,
    HospitalUpdate,
    HospitalResponse,
)
from api.utils.logger import get_logger

logger = get_logger("hospital_service")


class HospitalService:
    """Service for Hospital operations using Beanie"""

    @staticmethod
    async def create_hospital(hospital_data: HospitalCreate) -> dict:
        """Create a new hospital"""
        try:

            existing_hospital = await Hospital.find_one({"name": hospital_data.name})

            if existing_hospital:
                return {
                    "success": False,
                    "message": f"Hospital with name '{hospital_data.name}' already exists",
                    "data": {}
                }

            hospital = Hospital(name=hospital_data.name, address=hospital_data.address)

            await hospital.insert()
            logger.info(f"Hospital created: {hospital.name}")

            return {
                "success": True,
                "message": "Hospital created successfully",
                "data": HospitalResponse(
                    id=str(hospital.id),
                    name=hospital.name,
                    address=hospital.address,
                    created_at=hospital.created_at,
                    updated_at=hospital.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error creating hospital: {e}")
            return {
                "success": False,
                "message": f"Failed to create hospital: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_hospital(hospital_id: str) -> dict:
        """Get hospital by ID"""
        try:
            if not ObjectId.is_valid(hospital_id):
                return {
                    "success": False,
                    "message": "Invalid hospital ID format",
                    "data": None,
                }

            hospital = await Hospital.get(ObjectId(hospital_id))
            if not hospital:
                return {"success": False, "message": "Hospital not found", "data": None}

            return {
                "success": True,
                "message": "Hospital retrieved successfully",
                "data": HospitalResponse(
                    id=str(hospital.id),
                    name=hospital.name,
                    address=hospital.address,
                    created_at=hospital.created_at,
                    updated_at=hospital.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error getting hospital: {e}")
            return {
                "success": False,
                "message": f"Failed to get hospital: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_all_hospitals(skip: int = 0, limit: int = 100) -> dict:
        """Get all hospitals with pagination"""
        try:
            hospitals = await Hospital.find_all().skip(skip).limit(limit).to_list()

            hospital_list = [
                HospitalResponse(
                    id=str(hospital.id),
                    name=hospital.name,
                    address=hospital.address,
                    created_at=hospital.created_at,
                    updated_at=hospital.updated_at,
                )
                for hospital in hospitals
            ]

            return {
                "success": True,
                "message": f"Retrieved {len(hospital_list)} hospitals",
                "data": hospital_list,
            }
        except Exception as e:
            logger.error(f"Error getting hospitals: {e}")
            return {
                "success": False,
                "message": f"Failed to get hospitals: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def update_hospital(hospital_id: str, hospital_data: HospitalUpdate) -> dict:
        """Update hospital by ID"""
        try:
            if not ObjectId.is_valid(hospital_id):
                return {
                    "success": False,
                    "message": "Invalid hospital ID format",
                    "data": None,
                }

            hospital = await Hospital.get(ObjectId(hospital_id))
            if not hospital:
                return {"success": False, "message": "Hospital not found", "data": None}

            # Update fields if provided
            update_data = hospital_data.dict(exclude_unset=True)
            if update_data:
                for field, value in update_data.items():
                    setattr(hospital, field, value)

                hospital.update_timestamp()
                await hospital.save()

            return {
                "success": True,
                "message": "Hospital updated successfully",
                "data": HospitalResponse(
                    id=str(hospital.id),
                    name=hospital.name,
                    address=hospital.address,
                    created_at=hospital.created_at,
                    updated_at=hospital.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error updating hospital: {e}")
            return {
                "success": False,
                "message": f"Failed to update hospital: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def delete_hospital(hospital_id: str) -> dict:
        """Delete hospital by ID"""
        try:
            if not ObjectId.is_valid(hospital_id):
                return {
                    "success": False,
                    "message": "Invalid hospital ID format",
                    "data": None,
                }

            hospital = await Hospital.get(ObjectId(hospital_id))
            if not hospital:
                return {"success": False, "message": "Hospital not found", "data": None}

            await hospital.delete()
            logger.info(f"Hospital deleted: {hospital.name}")

            return {
                "success": True,
                "message": "Hospital deleted successfully",
                "data": None,
            }
        except Exception as e:
            logger.error(f"Error deleting hospital: {e}")
            return {
                "success": False,
                "message": f"Failed to delete hospital: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def search_hospitals(query: str, skip: int = 0, limit: int = 100) -> dict:
        """Search hospitals by name or address"""
        try:
            # Create regex pattern for case-insensitive search
            import re

            pattern = re.compile(query, re.IGNORECASE)

            hospitals = (
                await Hospital.find(
                    {
                        "$or": [
                            {"name": {"$regex": pattern}},
                            {"address": {"$regex": pattern}},
                        ]
                    }
                )
                .skip(skip)
                .limit(limit)
                .to_list()
            )

            hospital_list = [
                HospitalResponse(
                    id=str(hospital.id),
                    name=hospital.name,
                    address=hospital.address,
                    created_at=hospital.created_at,
                    updated_at=hospital.updated_at,
                )
                for hospital in hospitals
            ]

            return {
                "success": True,
                "message": f"Found {len(hospital_list)} hospitals matching '{query}'",
                "data": hospital_list,
            }
        except Exception as e:
            logger.error(f"Error searching hospitals: {e}")
            return {
                "success": False,
                "message": f"Failed to search hospitals: {str(e)}",
                "data": None,
            }
