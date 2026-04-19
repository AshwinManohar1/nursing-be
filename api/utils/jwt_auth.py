from datetime import datetime, timedelta
from typing import Optional, Dict
from uuid import uuid4
import jwt
from api.config import (
    JWT_PRIVATE_KEY,
    JWT_PUBLIC_KEY,
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
)
from api.utils.logger import get_logger

logger = get_logger("jwt_auth")

JWT_ALGORITHM = "RS256"


def _get_signing_key():
    """Private key for RS256 signing."""
    if not JWT_PRIVATE_KEY:
        raise ValueError("JWT_PRIVATE_KEY is required for RS256")
    return JWT_PRIVATE_KEY.replace("\\n", "\n")


def _get_verification_key():
    """Public key for RS256 verification."""
    if not JWT_PUBLIC_KEY:
        raise ValueError("JWT_PUBLIC_KEY is required for RS256")
    return JWT_PUBLIC_KEY.replace("\\n", "\n")


class JWTAuth:
    """JWT authentication utilities"""

    @staticmethod
    def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT access token with jti for revocation support.
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode = data.copy()
        to_encode.update({
            "jti": str(uuid4()),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
        })

        return jwt.encode(to_encode, _get_signing_key(), algorithm=JWT_ALGORITHM)

    @staticmethod
    def create_refresh_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT refresh token with jti for revocation support.
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)

        to_encode = data.copy()
        to_encode.update({
            "jti": str(uuid4()),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
        })

        return jwt.encode(to_encode, _get_signing_key(), algorithm=JWT_ALGORITHM)

    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Optional[Dict]:
        """
        Verify and decode a JWT token.
        """
        try:
            payload = jwt.decode(
                token, _get_verification_key(), algorithms=[JWT_ALGORITHM]
            )

            if payload.get("type") != token_type:
                logger.warning(f"Token type mismatch. Expected {token_type}, got {payload.get('type')}")
                return None

            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error verifying token: {str(e)}")
            return None

    @staticmethod
    def get_user_from_token(token: str) -> Optional[Dict]:
        """
        Extract user information from access token.
        """
        payload = JWTAuth.verify_token(token, token_type="access")
        if payload:
            return {
                "user_id": payload.get("user_id"),
                "employee_id": payload.get("employee_id"),
                "role": payload.get("role"),
                "org_id": payload.get("org_id"),
            }
        return None
