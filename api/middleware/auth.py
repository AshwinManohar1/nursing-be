from functools import wraps
from typing import Callable, Dict, List, Optional
from bson import ObjectId
from fastapi import HTTPException, Request, status
from api.models.user import User
from api.models.revoked_token import RevokedToken
from api.utils.jwt_auth import JWTAuth
from api.config import SUPER_ADMIN_SECRET_KEY
from api.utils.logger import get_logger
import inspect

logger = get_logger("auth_middleware")

# Cache function signatures to avoid repeated inspect calls
_signature_cache: Dict[Callable, List[str]] = {}


async def _verify_user_token_and_role(
    token: str,
    allowed_roles: List[str],
    verify_user_status: bool = False
) -> Dict:
    """
    Verify JWT token and check if user role is allowed.
    
    Args:
        token: JWT access token
        allowed_roles: List of allowed roles
        verify_user_status: If True, checks user status in DB (adds latency). Default: False
        
    Returns:
        Dictionary with user information
        
    Raises:
        HTTPException: If token is invalid or role not allowed
    """
    payload = JWTAuth.verify_token(token, token_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token was revoked (logout)
    jti = payload.get("jti")
    if jti:
        revoked = await RevokedToken.find_one(RevokedToken.jti == jti)
        if revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user_id = payload.get("user_id")
    role = payload.get("role")
    employee_id = payload.get("employee_id")
    org_id = payload.get("org_id")
    staff_id = payload.get("staff_id")  # Include staff_id in token if needed

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check role from token (fast, no DB call)
    if role not in allowed_roles:
        logger.warning(f"User {employee_id} with role {role} attempted to access route requiring {allowed_roles}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Required roles: {', '.join(allowed_roles)}",
        )

    # Optional: Verify user status in DB (only if explicitly requested)
    # This adds latency but ensures user is still active
    if verify_user_status:
        try:
            user = await User.get(ObjectId(user_id))
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if user.status != "ACTIVE":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User account is {user.status.lower()}. Please contact administrator.",
                )
            
            # Use staff_id from DB if available
            staff_id = str(user.staff_id) if user.staff_id else staff_id
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error verifying user status: {e}")
            # Don't fail the request if DB check fails, trust the token
            pass

    # Return user info from token (fast, no DB call)
    return {
        "user_id": user_id,
        "employee_id": employee_id,
        "role": role,
        "org_id": org_id,
        "staff_id": staff_id,
    }


def require_roles(allowed_roles: List[str]):
    """
    Decorator to require specific roles for a route (uses Bearer token).
    
    Usage:
        @router.get("/protected")
        @require_roles(["SUPER_ADMIN", "ADMIN"])
        async def protected_route(request: Request, current_user: dict):
            return {"message": "Access granted"}
    
    Args:
        allowed_roles: List of roles that are allowed to access the route
    """
    def decorator(func: Callable) -> Callable:
        # Cache function signature once at decoration time (not on every request)
        if func not in _signature_cache:
            sig = inspect.signature(func)
            _signature_cache[func] = list(sig.parameters.keys())
        param_names = _signature_cache[func]
        has_current_user = 'current_user' in param_names
        
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            authorization = request.headers.get("Authorization")
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authorization header missing or invalid",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            token = authorization.replace("Bearer ", "")
            current_user_data = await _verify_user_token_and_role(token, allowed_roles)

            # Inject current_user if parameter exists (using cached check)
            if has_current_user:
                kwargs['current_user'] = current_user_data

            return await func(request=request, *args, **kwargs)

        return wrapper
    return decorator


def require_super_admin_or_secret():
    """
    Decorator for user routes that accepts either:
    1. Secret key (X-Secret-Key header) - for initial setup
    2. SUPER_ADMIN Bearer token - for authenticated super admin
    
    Usage:
        @router.post("/users")
        @require_super_admin_or_secret()
        async def create_user(request: Request, user: UserCreate, current_user: Optional[dict] = None):
            # current_user will be None if using secret key
            # current_user will contain user info if using token
            return {"message": "User created"}
    """
    def decorator(func: Callable) -> Callable:
        # Cache function signature once at decoration time (not on every request)
        if func not in _signature_cache:
            sig = inspect.signature(func)
            _signature_cache[func] = list(sig.parameters.keys())
        param_names = _signature_cache[func]
        has_current_user = 'current_user' in param_names
        
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Check for secret key first
            secret_key = request.headers.get("X-Secret-Key")
            if secret_key and secret_key == SUPER_ADMIN_SECRET_KEY:
                # Secret key authentication - set current_user to None if parameter exists
                if has_current_user:
                    kwargs['current_user'] = None
                return await func(request=request, *args, **kwargs)
            
            # If no valid secret key, check for Bearer token
            authorization = request.headers.get("Authorization")
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authorization required. Provide X-Secret-Key header or Bearer token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            token = authorization.replace("Bearer ", "")
            # Verify token and ensure it's SUPER_ADMIN
            current_user_data = await _verify_user_token_and_role(token, ["SUPER_ADMIN"])

            # Set current_user if parameter exists (using cached check)
            if has_current_user:
                kwargs['current_user'] = current_user_data

            return await func(request=request, *args, **kwargs)

        return wrapper
    return decorator


# Convenience decorators
def require_admin():
    """Decorator that requires ADMIN or SUPER_ADMIN role"""
    return require_roles(["SUPER_ADMIN", "ADMIN"])
