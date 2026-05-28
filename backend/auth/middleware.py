"""
FastAPI dependency for authenticated routes.

Usage in any route:
    current_user: User = Depends(get_current_user)

This:
  1. Extracts the Bearer token from the Authorization header
  2. Decodes and validates the JWT
  3. Loads the User row from DB
  4. Returns the User object — or raises 401 if anything fails
"""

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.auth.jwt_handler import decode_access_token
from backend.database import get_db
from backend.models.db import User

logger = structlog.get_logger()

# FastAPI's built-in Bearer token extractor — reads Authorization: Bearer <token>
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that validates the JWT and returns the authenticated User.
    Inject this into any route that requires login.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        user_id = decode_access_token(credentials.credentials)
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning("jwt_user_not_found", user_id=user_id)
        raise credentials_exception

    return user
