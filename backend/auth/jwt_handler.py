"""
JWT utilities for issuing and verifying our own session tokens.

After Zoho OAuth succeeds, we give the frontend a JWT.
The frontend includes it in every request as: Authorization: Bearer <token>
We never pass Zoho tokens to the frontend — they stay server-side only.
"""

from datetime import UTC, datetime, timedelta

import structlog
from jose import JWTError, jwt

from backend.config import settings

logger = structlog.get_logger()

ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    """
    Creates a signed JWT encoding the user's internal DB id.
    Expires after ACCESS_TOKEN_EXPIRE_MINUTES (default: 1440 = 24 hours).
    """
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),   # subject — the user's internal DB id
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """
    Decodes and validates a JWT.
    Returns the user_id (int) on success.
    Raises JWTError if the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise JWTError("Token missing subject")
        return int(user_id_str)
    except JWTError:
        logger.warning("jwt_decode_failed")
        raise
