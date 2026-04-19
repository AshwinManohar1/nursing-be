"""Model for revoked JWT tokens (blocklist). Used for logout token invalidation."""
from datetime import datetime
from beanie import Document, Indexed


class RevokedToken(Document):
    """Revoked token (jti) - stored until token expiry for blocklist check."""

    jti: str = Indexed(unique=True)
    expires_at: datetime

    class Settings:
        name = "revoked_tokens"
