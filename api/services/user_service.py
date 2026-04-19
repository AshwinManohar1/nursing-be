from typing import Optional, List
from bson import ObjectId
import hashlib
import secrets
from api.models.user import (
    User,
    UserCreate,
    UserUpdate,
    UserResponse,
)
from api.models.staff import Staff
from api.models.revoked_token import RevokedToken
from api.utils.logger import get_logger
from api.config import JWT_ACCESS_TOKEN_EXPIRE_MINUTES
from api.utils.jwt_auth import JWTAuth
from datetime import datetime


logger = get_logger("user_service")


class UserService:
    """Service for User operations using Beanie"""

    @staticmethod
    def _generate_salt() -> str:
        """Generate a random salt for password hashing"""
        return secrets.token_hex(32)

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Hash password using PBKDF2 with salt"""
        # Using PBKDF2 with SHA-256, 100000 iterations
        password_bytes = password.encode('utf-8')
        salt_bytes = salt.encode('utf-8')
        hash_obj = hashlib.pbkdf2_hmac('sha256', password_bytes, salt_bytes, 100000)
        return hash_obj.hex()

    @staticmethod
    def _verify_password(password: str, salt: str, password_hash: str) -> bool:
        """Verify password against stored hash"""
        computed_hash = UserService._hash_password(password, salt)
        return computed_hash == password_hash

    @staticmethod
    async def _validate_staff_id_for_role(role: str, staff_id: Optional[str], employee_id: str) -> tuple[bool, Optional[str]]:
        """
        Validate staff_id requirements based on role.
        Returns: (is_valid, error_message)
        """
        # SUPER_ADMIN doesn't require staff_id
        if role == "SUPER_ADMIN":
            return True, None
        
        # ADMIN, WARD_INCHARGE, and STAFF require staff_id
        if not staff_id:
            return False, f"staff_id is required for {role} role"
        
        if not ObjectId.is_valid(staff_id):
            return False, "Invalid staff_id format"
        
        staff = await Staff.get(ObjectId(staff_id))
        if not staff:
            return False, f"Staff with id '{staff_id}' not found"
        
        # Validate that staff.emp_id matches the employee_id
        if staff.emp_id != employee_id:
            return False, (
                f"Employee ID mismatch: User employee_id '{employee_id}' does not match "
                f"Staff emp_id '{staff.emp_id}'"
            )
        
        # For WARD_INCHARGE, validate position
        if role == "WARD_INCHARGE":
            if staff.position != "ward_incharge":
                return False, (
                    f"Cannot assign WARD_INCHARGE role: Staff position is '{staff.position}', "
                    f"expected 'ward_incharge'"
                )
        
        return True, None

    @staticmethod
    async def create_user(user_data: UserCreate) -> dict:
        """Create a new user"""
        try:
            # Check if user with same employee_id already exists
            existing_user = await User.find_one({"employee_id": user_data.employee_id})
            if existing_user:
                return {
                    "success": False,
                    "message": f"User with employee_id '{user_data.employee_id}' already exists",
                    "data": None
                }
            
            # Validate staff_id based on role
            is_valid, error_msg = await UserService._validate_staff_id_for_role(
                user_data.role, user_data.staff_id, user_data.employee_id
            )
            if not is_valid:
                return {
                    "success": False,
                    "message": error_msg,
                    "data": None
                }
            
            # Generate salt and hash password
            salt = UserService._generate_salt()
            password_hash = UserService._hash_password(user_data.password, salt)
            
            # Create user
            user = User(
                employee_id=user_data.employee_id,
                salt=salt,
                password_hash=password_hash,
                role=user_data.role,
                staff_id=ObjectId(user_data.staff_id) if user_data.staff_id else None,
                status="ACTIVE"
            )
            
            await user.insert()
            logger.info(f"User created: {user.employee_id} with role {user.role}")
            
            return {
                "success": True,
                "message": "User created successfully",
                "data": UserResponse(
                    id=str(user.id),
                    employee_id=user.employee_id,
                    role=user.role,
                    staff_id=str(user.staff_id) if user.staff_id else None,
                    status=user.status,
                    last_login=user.last_login,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return {
                "success": False,
                "message": f"Failed to create user: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_user(user_id: str) -> dict:
        """Get user by ID"""
        try:
            if not ObjectId.is_valid(user_id):
                return {
                    "success": False,
                    "message": "Invalid user ID format",
                    "data": None,
                }
            
            user = await User.get(ObjectId(user_id))
            if not user:
                return {"success": False, "message": "User not found", "data": None}
            
            return {
                "success": True,
                "message": "User retrieved successfully",
                "data": UserResponse(
                    id=str(user.id),
                    employee_id=user.employee_id,
                    role=user.role,
                    staff_id=str(user.staff_id) if user.staff_id else None,
                    status=user.status,
                    last_login=user.last_login,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return {
                "success": False,
                "message": f"Failed to get user: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_user_by_employee_id(employee_id: str) -> dict:
        """Get user by employee_id"""
        try:
            user = await User.find_one({"employee_id": employee_id})
            if not user:
                return {"success": False, "message": "User not found", "data": None}
            
            return {
                "success": True,
                "message": "User retrieved successfully",
                "data": UserResponse(
                    id=str(user.id),
                    employee_id=user.employee_id,
                    role=user.role,
                    staff_id=str(user.staff_id) if user.staff_id else None,
                    status=user.status,
                    last_login=user.last_login,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error getting user by employee_id: {e}")
            return {
                "success": False,
                "message": f"Failed to get user: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def get_all_users(skip: int = 0, limit: int = 100, role: Optional[str] = None, status: Optional[str] = None) -> dict:
        """Get all users with pagination and filtering"""
        try:
            # Build filter query
            filter_query = {}
            if role:
                filter_query["role"] = role.upper()
            if status:
                filter_query["status"] = status.upper()
            
            # Get users from database
            users = await User.find(filter_query).skip(skip).limit(limit).to_list()
            
            user_responses = []
            for user in users:
                user_responses.append(UserResponse(
                    id=str(user.id),
                    employee_id=user.employee_id,
                    role=user.role,
                    staff_id=str(user.staff_id) if user.staff_id else None,
                    status=user.status,
                    last_login=user.last_login,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                ))
            
            return {
                "success": True,
                "message": f"Retrieved {len(user_responses)} users",
                "data": user_responses,
            }
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return {
                "success": False,
                "message": f"Failed to get users: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def update_user(user_id: str, user_data: UserUpdate) -> dict:
        """Update user by ID"""
        try:
            if not ObjectId.is_valid(user_id):
                return {
                    "success": False,
                    "message": "Invalid user ID format",
                    "data": None,
                }
            
            user = await User.get(ObjectId(user_id))
            if not user:
                return {"success": False, "message": "User not found", "data": None}
            
            # Get current role and employee_id for validation
            current_role = user.role
            current_employee_id = user.employee_id
            new_role = user_data.role if user_data.role else current_role
            new_employee_id = user_data.employee_id if user_data.employee_id else current_employee_id
            
            # If role or employee_id is being updated, validate staff_id
            if user_data.role or user_data.employee_id or user_data.staff_id:
                staff_id_to_validate = user_data.staff_id if user_data.staff_id else (str(user.staff_id) if user.staff_id else None)
                is_valid, error_msg = await UserService._validate_staff_id_for_role(
                    new_role, staff_id_to_validate, new_employee_id
                )
                if not is_valid:
                    return {
                        "success": False,
                        "message": error_msg,
                        "data": None
                    }
            
            # Update fields if provided
            update_data = user_data.dict(exclude_unset=True)
            if update_data:
                for field, value in update_data.items():
                    if field == "password":
                        # Hash new password
                        salt = UserService._generate_salt()
                        password_hash = UserService._hash_password(value, salt)
                        setattr(user, "salt", salt)
                        setattr(user, "password_hash", password_hash)
                    elif field == "staff_id" and value:
                        setattr(user, field, ObjectId(value))
                    elif field == "staff_id" and value is None:
                        setattr(user, field, None)
                    else:
                        setattr(user, field, value)
                
                user.update_timestamp()
                await user.save()
            
            return {
                "success": True,
                "message": "User updated successfully",
                "data": UserResponse(
                    id=str(user.id),
                    employee_id=user.employee_id,
                    role=user.role,
                    staff_id=str(user.staff_id) if user.staff_id else None,
                    status=user.status,
                    last_login=user.last_login,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                ),
            }
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return {
                "success": False,
                "message": f"Failed to update user: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def delete_user(user_id: str) -> dict:
        """Delete user by ID"""
        try:
            if not ObjectId.is_valid(user_id):
                return {
                    "success": False,
                    "message": "Invalid user ID format",
                    "data": None,
                }
            
            user = await User.get(ObjectId(user_id))
            if not user:
                return {"success": False, "message": "User not found", "data": None}
            
            await user.delete()
            logger.info(f"User deleted: {user.employee_id}")
            
            return {
                "success": True,
                "message": "User deleted successfully",
                "data": None,
            }
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return {
                "success": False,
                "message": f"Failed to delete user: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def verify_login(employee_id: str, password: str) -> dict:
        """Verify user login credentials"""
        try:
            user = await User.find_one({"employee_id": employee_id})
            if not user:
                return {
                    "success": False,
                    "message": "Invalid employee_id or password",
                    "data": None,
                }
            
            # Check if user is active
            if user.status != "ACTIVE":
                return {
                    "success": False,
                    "message": f"User account is {user.status.lower()}. Please contact administrator.",
                    "data": None,
                }
            
            # Verify password
            if not UserService._verify_password(password, user.salt, user.password_hash):
                return {
                    "success": False,
                    "message": "Invalid employee_id or password",
                    "data": None,
                }
            
            # Fetch staff details if staff_id exists to get org_id (hospital_id), name, and ward_id
            org_id = None
            name = None
            ward_id = None
            if user.staff_id:
                staff = await Staff.get(user.staff_id)
                if staff:
                    org_id = str(staff.hospital_id)
                    name = staff.name
                    ward_id = [str(ward) for ward in staff.ward_id] if staff.ward_id else None
            
            # Update last_login
            user.last_login = datetime.utcnow()
            user.update_timestamp()
            await user.save()
            
            # Generate JWT tokens
            # Include all necessary info in token to avoid DB lookups and prevent client-side spoofing
            access_token_data = {
                "user_id": str(user.id),
                "employee_id": user.employee_id,
                "role": user.role,
                "org_id": org_id,
                "staff_id": str(user.staff_id) if user.staff_id else None,
                "ward_id": ward_id,
                "name": name,
            }
            
            refresh_token_data = {
                "user_id": str(user.id),
                "employee_id": user.employee_id,
            }
            
            access_token = JWTAuth.create_access_token(access_token_data)
            refresh_token = JWTAuth.create_refresh_token(refresh_token_data)
            
            # Build login response with org_id, name, ward_id, and tokens
            login_data = {
                "id": str(user.id),
                "employee_id": user.employee_id,
                "name": name,
                "role": user.role,
                "org_id": org_id,
                "staff_id": str(user.staff_id) if user.staff_id else None,
                "ward_id": ward_id,
                "status": user.status,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat(),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # in seconds
            }
            
            return {
                "success": True,
                "message": "Login successful",
                "data": login_data,
            }
        except Exception as e:
            logger.error(f"Error verifying login: {e}")
            return {
                "success": False,
                "message": f"Failed to verify login: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def refresh_access_token(refresh_token: str) -> dict:
        """Refresh access token using refresh token"""
        try:
            # Verify refresh token
            payload = JWTAuth.verify_token(refresh_token, token_type="refresh")
            if not payload:
                return {
                    "success": False,
                    "message": "Invalid or expired refresh token",
                    "data": None,
                }
            
            # Get user from token
            user_id = payload.get("user_id")
            employee_id = payload.get("employee_id")
            
            if not user_id or not employee_id:
                return {
                    "success": False,
                    "message": "Invalid token payload",
                    "data": None,
                }
            
            # Verify user still exists and is active
            user = await User.get(ObjectId(user_id))
            if not user:
                return {
                    "success": False,
                    "message": "User not found",
                    "data": None,
                }
            
            if user.status != "ACTIVE":
                return {
                    "success": False,
                    "message": f"User account is {user.status.lower()}. Please contact administrator.",
                    "data": None,
                }
            
            # Verify employee_id matches
            if user.employee_id != employee_id:
                return {
                    "success": False,
                    "message": "Token validation failed",
                    "data": None,
                }
            
            # Fetch staff details if staff_id exists to get org_id, name, ward_id
            org_id = None
            name = None
            ward_id = None
            if user.staff_id:
                staff = await Staff.get(user.staff_id)
                if staff:
                    org_id = str(staff.hospital_id)
                    name = staff.name
                    ward_id = [str(ward) for ward in staff.ward_id] if staff.ward_id else None
            
            # Generate new access token (include all fields for token-derived user on frontend)
            access_token_data = {
                "user_id": str(user.id),
                "employee_id": user.employee_id,
                "role": user.role,
                "org_id": org_id,
                "staff_id": str(user.staff_id) if user.staff_id else None,
                "ward_id": ward_id,
                "name": name,
            }
            
            access_token = JWTAuth.create_access_token(access_token_data)
            
            # Return new access token
            return {
                "success": True,
                "message": "Token refreshed successfully",
                "data": {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # in seconds
                },
            }
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return {
                "success": False,
                "message": f"Failed to refresh token: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def logout(access_token: str) -> dict:
        """Revoke access token by adding jti to blocklist."""
        try:
            payload = JWTAuth.verify_token(access_token, token_type="access")
            if not payload:
                return {
                    "success": False,
                    "message": "Invalid or expired token",
                    "data": None,
                }
            jti = payload.get("jti")
            exp = payload.get("exp")
            if not jti or not exp:
                return {
                    "success": False,
                    "message": "Invalid token payload",
                    "data": None,
                }
            expires_at = datetime.utcfromtimestamp(exp)
            existing = await RevokedToken.find_one(RevokedToken.jti == jti)
            if not existing:
                await RevokedToken(jti=jti, expires_at=expires_at).insert()
            return {
                "success": True,
                "message": "Logged out successfully",
                "data": None,
            }
        except Exception as e:
            logger.error(f"Error during logout: {e}")
            return {
                "success": False,
                "message": f"Logout failed: {str(e)}",
                "data": None,
            }