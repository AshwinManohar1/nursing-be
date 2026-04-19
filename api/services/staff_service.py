from typing import List, Optional, Dict
from bson import ObjectId
from api.models.staff import (
    Staff,
    StaffCreate,
    StaffUpdate,
    StaffResponse,
)
from api.models.ward import Ward
from api.utils.logger import get_logger
from fastapi import UploadFile
import csv
import io

logger = get_logger("staff_service")


class StaffService:
    """Service for Staff operations using Beanie"""

    @staticmethod
    async def create_staff(staff_data: StaffCreate, current_user: Optional[dict] = None) -> dict:
        """Create a new staff member"""
        try:
            # Validate WARD_INCHARGE permissions
            if current_user and current_user.get("role") == "WARD_INCHARGE":
                # WARD_INCHARGE must provide ward_id
                if not staff_data.ward_id or len(staff_data.ward_id) == 0:
                    return {
                        "success": False,
                        "message": "ward_id is required when creating staff as WARD_INCHARGE",
                        "data": None
                    }
                
                # Get WARD_INCHARGE's staff record to check their managed wards
                staff_id = current_user.get("staff_id")
                if not staff_id:
                    return {
                        "success": False,
                        "message": "Unable to verify ward access: staff_id not found",
                        "data": None
                    }
                
                incharge_staff = await Staff.get(ObjectId(staff_id))
                if not incharge_staff:
                    return {
                        "success": False,
                        "message": "Unable to verify ward access: staff record not found",
                        "data": None
                    }
                
                # Get list of ward IDs the WARD_INCHARGE manages
                incharge_ward_ids = [str(w) for w in incharge_staff.ward_id] if incharge_staff.ward_id else []
                if not incharge_ward_ids:
                    return {
                        "success": False,
                        "message": "You are not assigned to any wards. Cannot create staff.",
                        "data": None
                    }
                
                # Validate all provided ward_ids are in their managed wards
                provided_ward_ids = [str(w) for w in staff_data.ward_id]
                invalid_wards = [w for w in provided_ward_ids if w not in incharge_ward_ids]
                if invalid_wards:
                    return {
                        "success": False,
                        "message": f"Cannot create staff for wards you don't manage: {invalid_wards}",
                        "data": None
                    }
            
            # Check if staff with same email already exists (only if email provided)
            if staff_data.email:
                existing_staff = await Staff.find_one({"email": staff_data.email})
                if existing_staff:
                    return {
                        "success": False,
                        "message": f"Staff with email '{staff_data.email}' already exists",
                        "data": None
                    }
            # Check if staff with same emp_id already exists (emp_id must be unique)
            existing_emp = await Staff.find_one({"emp_id": staff_data.emp_id})
            if existing_emp:
                return {
                    "success": False,
                    "message": f"Staff with emp_id '{staff_data.emp_id}' already exists",
                    "data": None
                }

            staff = Staff(
                name=staff_data.name,
                email=staff_data.email if staff_data.email else None,
                contact_no=staff_data.contact_no,
                emp_id=staff_data.emp_id,
                grade=staff_data.grade,
                gender=staff_data.gender,
                position=staff_data.position,
                hospital_id=ObjectId(staff_data.hospital_id),
                ward_id=[ObjectId(ward_id) for ward_id in staff_data.ward_id] if staff_data.ward_id else None
            )

            await staff.insert()
            logger.info(f"Staff created: {staff.name}")

            return {
                "success": True,
                "message": "Staff created successfully",
                "data": StaffResponse(
                    id=str(staff.id),
                    name=staff.name,
                    email=staff.email,
                    contact_no=staff.contact_no,
                    emp_id=staff.emp_id,
                    grade=staff.grade,
                    gender=staff.gender,
                    position=staff.position,
                    hospital_id=str(staff.hospital_id),
                    ward_id=[str(ward_id) for ward_id in staff.ward_id] if staff.ward_id else None,
                    created_at=staff.created_at,
                    updated_at=staff.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error creating staff: {e}")
            return {
                "success": False,
                "message": f"Failed to create staff: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_staff(staff_id: str) -> dict:
        """Get staff by ID"""
        try:
            if not ObjectId.is_valid(staff_id):
                return {
                    "success": False,
                    "message": "Invalid staff ID format",
                    "data": None,
                }

            staff = await Staff.get(ObjectId(staff_id))
            if not staff:
                return {"success": False, "message": "Staff not found", "data": None}

            return {
                "success": True,
                "message": "Staff retrieved successfully",
                "data": StaffResponse(
                    id=str(staff.id),
                    name=staff.name,
                    email=staff.email,
                    contact_no=staff.contact_no,
                    emp_id=staff.emp_id,
                    grade=staff.grade,
                    gender=staff.gender,
                    position=staff.position,
                    hospital_id=str(staff.hospital_id),
                    ward_id=[str(ward_id) for ward_id in staff.ward_id] if staff.ward_id else None,
                    created_at=staff.created_at,
                    updated_at=staff.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error getting staff: {e}")
            return {
                "success": False,
                "message": f"Failed to get staff: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_all_staff(skip: int = 0, limit: int = 100, hospital_id: Optional[str] = None, ward_id: Optional[str] = None, grade: Optional[str] = None, search: Optional[str] = None, ward_ids: Optional[List[str]] = None) -> dict:
        """Get all staff with pagination, filtering, and search"""
        try:
            # Build filter query
            filter_query = {}
            if hospital_id:
                filter_query["hospital_id"] = ObjectId(hospital_id)
            if ward_ids:
                # Multiple ward_ids (for WARD_INCHARGE)
                filter_query["ward_id"] = {"$in": [ObjectId(w_id) for w_id in ward_ids]}
            elif ward_id:
                # Single ward_id
                filter_query["ward_id"] = ObjectId(ward_id)
            if grade:
                filter_query["grade"] = grade
            
            # Add search functionality - search across name, email, and emp_id
            if search and search.strip():
                search_term = search.strip()
                # Use case-insensitive regex for MongoDB search
                search_regex = {"$regex": search_term, "$options": "i"}
                filter_query["$or"] = [
                    {"name": search_regex},
                    {"email": search_regex},
                    {"emp_id": search_regex}
                ]

            # Get total count for pagination
            total_count = await Staff.find(filter_query).count()

            # Get raw documents from database with sorting for consistent pagination
            # Sort by created_at descending (newest first) to ensure consistent ordering
            raw_staff_list = await Staff.find(filter_query).sort("-created_at").skip(skip).limit(limit).to_list()

            staff_responses = []
            for raw_staff in raw_staff_list:
                try:
                    # Convert raw document to Staff model to validate data
                    staff = Staff.model_validate(raw_staff.model_dump())
                    
                    staff_responses.append(StaffResponse(
                        id=str(staff.id),
                        name=staff.name,
                        email=staff.email,
                        contact_no=staff.contact_no,
                        emp_id=staff.emp_id,
                        grade=staff.grade,
                        gender=staff.gender,
                        position=staff.position,
                        hospital_id=str(staff.hospital_id),
                        ward_id=[str(ward_id) for ward_id in staff.ward_id] if staff.ward_id else None,
                        created_at=staff.created_at,
                        updated_at=staff.updated_at,
                    ))
                except Exception as validation_error:
                    logger.warning(f"Skipping invalid staff record {raw_staff.get('_id', 'unknown')}: {validation_error}")
                    continue

            # Calculate pagination metadata
            total_pages = (total_count + limit - 1) // limit if limit > 0 else 0
            current_page = (skip // limit) + 1 if limit > 0 else 1
            has_next = (skip + limit) < total_count
            has_prev = skip > 0

            return {
                "success": True,
                "message": f"Retrieved {len(staff_responses)} staff members",
                "data": {
                    "items": staff_responses,
                    "pagination": {
                        "total": total_count,
                        "limit": limit,
                        "offset": skip,
                        "current_page": current_page,
                        "total_pages": total_pages,
                        "has_next": has_next,
                        "has_prev": has_prev
                    }
                },
            }
        except Exception as e:
            logger.error(f"Error getting staff: {e}")
            return {
                "success": False,
                "message": f"Failed to get staff: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def update_staff(staff_id: str, staff_data: StaffUpdate) -> dict:
        """Update staff by ID"""
        try:
            if not ObjectId.is_valid(staff_id):
                return {
                    "success": False,
                    "message": "Invalid staff ID format",
                    "data": None,
                }

            staff = await Staff.get(ObjectId(staff_id))
            if not staff:
                return {"success": False, "message": "Staff not found", "data": None}

            # Update fields if provided
            update_data = staff_data.dict(exclude_unset=True)
            if update_data:
                # Enforce unique emp_id if being changed
                if "emp_id" in update_data and update_data["emp_id"] != staff.emp_id:
                    existing_emp = await Staff.find_one({"emp_id": update_data["emp_id"]})
                    if existing_emp and str(existing_emp.id) != str(staff.id):
                        return {
                            "success": False,
                            "message": f"Staff with emp_id '{update_data['emp_id']}' already exists",
                            "data": None,
                        }
                for field, value in update_data.items():
                    if field == "hospital_id" and value:
                        setattr(staff, field, ObjectId(value))
                    elif field == "ward_id" and value:
                        setattr(staff, field, [ObjectId(ward_id) for ward_id in value])
                    elif field == "ward_id" and value is None:
                        setattr(staff, field, None)
                    else:
                        setattr(staff, field, value)

                staff.update_timestamp()
                await staff.save()

            return {
                "success": True,
                "message": "Staff updated successfully",
                "data": StaffResponse(
                    id=str(staff.id),
                    name=staff.name,
                    email=staff.email,
                    contact_no=staff.contact_no,
                    emp_id=staff.emp_id,
                    grade=staff.grade,
                    gender=staff.gender,
                    position=staff.position,
                    hospital_id=str(staff.hospital_id),
                    ward_id=[str(ward_id) for ward_id in staff.ward_id] if staff.ward_id else None,
                    created_at=staff.created_at,
                    updated_at=staff.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error updating staff: {e}")
            return {
                "success": False,
                "message": f"Failed to update staff: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def delete_staff(staff_id: str) -> dict:
        """Delete staff by ID"""
        try:
            if not ObjectId.is_valid(staff_id):
                return {
                    "success": False,
                    "message": "Invalid staff ID format",
                    "data": None,
                }

            staff = await Staff.get(ObjectId(staff_id))
            if not staff:
                return {"success": False, "message": "Staff not found", "data": None}

            await staff.delete()
            logger.info(f"Staff deleted: {staff.name}")

            return {
                "success": True,
                "message": "Staff deleted successfully",
                "data": None,
            }
        except Exception as e:
            logger.error(f"Error deleting staff: {e}")
            return {
                "success": False,
                "message": f"Failed to delete staff: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_staff_by_ids(staff_ids: List[str]) -> dict:
        """Fetch staff details by a list of IDs"""
        try:
            if not staff_ids:
                return {
                    "success": False,
                    "message": "No staff IDs provided",
                    "data": None,
                }
            
            # Convert string IDs to ObjectIds
            object_ids = [ObjectId(staff_id) for staff_id in staff_ids]
            
            # Fetch staff records
            raw_staff_list = await Staff.find({"_id": {"$in": object_ids}}).to_list()
            
            if not raw_staff_list:
                return {
                    "success": False,
                    "message": "No staff found with provided IDs",
                    "data": None,
                }
            
            # Convert to roster format
            roster_staff = []
            for raw_staff in raw_staff_list:
                try:
                    # Convert raw document to Staff model to validate data
                    staff = Staff.model_validate(raw_staff.model_dump())
                    
                    roster_staff.append({
                        "id": str(staff.id),
                        "name": staff.name,
                        "grade": staff.grade,
                        "gender":staff.gender,
                        "email": staff.email,
                        "contact_no": staff.contact_no,
                        "emp_id": staff.emp_id,
                        "position": staff.position,
                        "hospital_id": str(staff.hospital_id),
                        "ward_id": [str(ward_id) for ward_id in staff.ward_id] if staff.ward_id else None,
                    })
                except Exception as validation_error:
                    logger.warning(f"Skipping invalid staff record {raw_staff.get('_id', 'unknown')}: {validation_error}")
                    continue
            
            return {
                "success": True,
                "message": "Staff details fetched successfully",
                "data": roster_staff,
            }
            
        except Exception as e:
            logger.error(f"Error getting staff by IDs: {e}")
            return {
                "success": False,
                "message": f"Failed to fetch staff details: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_nurses_by_ward(ward_id: str) -> dict:
        """Get all nurses assigned to a ward"""
        try:
            raw_nurses = await Staff.find({"ward_id": ObjectId(ward_id)}).to_list()
            
            nurse_responses = []
            for raw_nurse in raw_nurses:
                try:
                    # Convert raw document to Staff model to validate data
                    nurse = Staff.model_validate(raw_nurse.model_dump())
                    
                    nurse_responses.append(StaffResponse(
                        id=str(nurse.id),
                        name=nurse.name,
                        email=nurse.email,
                        contact_no=nurse.contact_no,
                        emp_id=nurse.emp_id,
                        grade=nurse.grade,
                        gender=nurse.gender,
                        position=nurse.position,
                        hospital_id=str(nurse.hospital_id),
                        ward_id=[str(ward_id) for ward_id in nurse.ward_id] if nurse.ward_id else None,
                        created_at=nurse.created_at,
                        updated_at=nurse.updated_at,
                    ))
                except Exception as validation_error:
                    logger.warning(f"Skipping invalid nurse record {raw_nurse.get('_id', 'unknown')}: {validation_error}")
                    continue
            
            return {
                "success": True,
                "message": f"Retrieved {len(nurse_responses)} nurses for ward",
                "data": nurse_responses,
            }
        except Exception as e:
            logger.error(f"Error getting nurses by ward: {e}")
            return {
                "success": False,
                "message": f"Failed to get nurses by ward: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def parse_csv_to_staff_list(csv_content: str, default_hospital_id: Optional[str] = None) -> List[Staff]:
        """Parse CSV content and convert to Staff objects"""
        staff_list = []
        csv_reader = csv.DictReader(io.StringIO(csv_content))

        if not default_hospital_id:
            raise ValueError("hospital_id is required for CSV parsing")

        hospital_id_value = ObjectId(default_hospital_id)

        position_mapping = {
            "nurse": "staff_nurse",
            "incharge": "ward_incharge",
            "in charge": "ward_incharge",
            "shift incharge": "shift_incharge",
            "shift_incharge": "shift_incharge",
        }

        def map_position(position: str) -> Optional[str]:
            if not position or not position.strip():
                return None 

            pos_lower = position.strip().lower()

            return position_mapping.get(pos_lower)

        for row in csv_reader:
            if not row.get("name") or row.get("name").strip() == "":
                continue

            try:
                email_value = row.get("email", "").strip()
                gender_value = row.get("gender", "").strip() if row.get("gender") else None
                contact_no_value = row.get("contact_no", "").strip() if row.get("contact_no") else None
                grade_value = row.get("grade", "").strip() if row.get("grade") else None                
                position_value = map_position(row.get("position", ""))
                if position_value is None:
                    logger.info(f"Skipping staff '{row.get('name', 'unknown')}' with excluded position '{row.get('position', '')}'")
                    continue

                ward_id_value = None

                if row.get("ward_id") and row.get("ward_id").strip():
                    ward_id_value = [ObjectId(ward_id.strip()) for ward_id in row.get("ward_id", "").split(",") if ward_id.strip()]

                elif row.get("department") and row.get("department").strip():
                    department_name = row.get("department", "").strip()
                    # Normalize department name to match Ward model's title() normalization
                    normalized_department = department_name.title()

                    ward = await Ward.find_one({
                        "$or": [
                            {"name": department_name, "hospital_id": hospital_id_value},
                            {"name": normalized_department, "hospital_id": hospital_id_value},
                            {"name": {"$regex": f"^{department_name}$", "$options": "i"}, "hospital_id": hospital_id_value}
                        ]
                    })

                    if ward:
                        ward_id_value = [ward.id]
                    else:
                        logger.warning(f"Ward '{department_name}' (normalized: '{normalized_department}') not found for hospital {default_hospital_id} for staff '{row.get('name', 'unknown')}'")

                staff = Staff(
                    name=row.get("name", "").strip(),
                    email=email_value if email_value else None,
                    contact_no=contact_no_value if contact_no_value else None,
                    emp_id=row.get("emp_id", "").strip(),
                    grade=grade_value if grade_value else None,
                    position=position_value,
                    gender=gender_value,
                    hospital_id=hospital_id_value,
                    ward_id=ward_id_value
                )
                staff_list.append(staff)
            except Exception as e:
                logger.warning(f"Skipping invalid CSV row for staff '{row.get('name', 'unknown')}': {e}")
                continue

        return staff_list

    @staticmethod
    async def upload_staff_file(file: UploadFile, hospital_id: str) -> dict:
        """Upload and process staff CSV file"""
        try:
            if not file.filename.endswith(".csv"):
                return {
                    "success": False,
                    "message": "Only CSV files are allowed",
                    "data": None,
                }

            content = await file.read()
            csv_content = content.decode("utf-8")

            staff_list = await StaffService.parse_csv_to_staff_list(csv_content, hospital_id)
            if not staff_list:
                return {
                    "success": False,
                    "message": "No valid staff data found in CSV",
                    "data": None,
                }

            inserted_count = 0
            failed_records = []
            seen_emp_ids = set()

            for staff in staff_list:
                try:
                    # Skip duplicates within the same file
                    if staff.emp_id in seen_emp_ids:
                        failed_records.append({"name": staff.name, "error": f"Duplicate emp_id '{staff.emp_id}' in file"})
                        continue
                    seen_emp_ids.add(staff.emp_id)

                    # Skip if emp_id already exists in DB
                    existing_emp = await Staff.find_one({"emp_id": staff.emp_id})
                    if existing_emp:
                        failed_records.append({"name": staff.name, "error": f"Staff with emp_id '{staff.emp_id}' already exists"})
                        continue

                    await staff.insert()
                    inserted_count += 1
                except Exception as e:
                    failed_records.append({"name": staff.name, "error": str(e)})

            response_data = {
                "total_records": len(staff_list),
                "inserted_count": inserted_count,
                "failed_count": len(failed_records),
                "failed_records": failed_records,
            }

            if failed_records:
                return {
                    "success": True,
                    "message": f"Upload completed with {inserted_count} successful and {len(failed_records)} failed records",
                    "data": response_data,
                }
            else:
                return {
                    "success": True,
                    "message": f"Successfully uploaded {inserted_count} staff records",
                    "data": response_data,
                }

        except Exception as e:
            logger.error(f"Error processing staff upload: {e}")
            return {
                "success": False,
                "message": f"Failed to process upload: {str(e)}",
                "data": None,
            }