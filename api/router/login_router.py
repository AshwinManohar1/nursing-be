from fastapi import APIRouter, HTTPException, Request, status
from api.services.user_service import UserService
from api.models.user import UserLogin, RefreshTokenRequest
from api.types.responses import ApiResponse
from api.utils.rate_limit import limiter, LOGIN_RATE_LIMIT

router = APIRouter(prefix="/api/v1", tags=["Authentication"])


@router.post(
    "/login",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="User login",
    description="Authenticate user with employee_id and password"
)
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(request: Request, login_data: UserLogin) -> ApiResponse:
    """
    Authenticate user and return login details with JWT tokens.
    """
    try:
        result = await UserService.verify_login(login_data.employee_id, login_data.password)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=result["message"]
            )
        return ApiResponse.ok("Login successful", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@router.post(
    "/refresh",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Refresh access token using refresh token"
)
async def refresh_token(token_data: RefreshTokenRequest) -> ApiResponse:
    """
    Refresh access token using refresh token.
    
    - **refresh_token**: JWT refresh token received during login
    
    Returns:
    - **access_token**: New JWT access token (expires in 12 hours)
    - **token_type**: "bearer"
    - **expires_in**: Access token expiration time in seconds
    """
    try:
        result = await UserService.refresh_access_token(token_data.refresh_token)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=result["message"]
            )
        return ApiResponse.ok("Token refreshed successfully", result.get("data"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )


@router.post(
    "/logout",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout",
    description="Revoke access token (invalidates it immediately)"
)
async def logout(request: Request) -> ApiResponse:
    """
    Logout and revoke the current access token.
    Requires Authorization: Bearer <access_token> header.
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.replace("Bearer ", "")
    result = await UserService.logout(token)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result["message"],
        )
    return ApiResponse.ok(result["message"], result.get("data"))
