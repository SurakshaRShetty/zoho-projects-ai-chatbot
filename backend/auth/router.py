"""
Auth routes:
  GET /auth/login      → redirect browser to Zoho consent page
  GET /auth/callback   → receive code from Zoho, store tokens, issue JWT, redirect to frontend
  GET /auth/me         → return current user profile (requires JWT)
  GET /auth/logout     → frontend calls this to clear session
"""

import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt_handler import create_access_token
from backend.auth.middleware import get_current_user
from backend.auth.oauth import zoho_oauth
from backend.config import settings
from backend.database import get_db
from backend.models.db import User
from backend.models.schemas import TokenResponse, UserProfile

logger = structlog.get_logger()
router = APIRouter()

# In-memory CSRF state store (state_token → True)
# In production, use Redis with a short TTL
_pending_states: dict[str, bool] = {}


@router.get("/login")
async def login() -> RedirectResponse:
    """
    Step 1 of OAuth: generate a CSRF state token and redirect the browser
    to Zoho's consent page. The user logs in there and approves our app.
    """
    state = secrets.token_urlsafe(32)
    _pending_states[state] = True

    auth_url = zoho_oauth.get_authorization_url(state)
    logger.info("oauth_login_initiated", state=state[:8] + "...")
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(
    code: str = Query(..., description="Authorization code from Zoho"),
    state: str = Query(..., description="CSRF state token"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Step 2 of OAuth: Zoho redirects here with the authorization code.
    We exchange it for tokens, store them, and issue a JWT to the frontend.
    Then redirect the browser to the chat page with the JWT in the URL.
    """
    # CSRF check — state must match what we generated in /login
    if state not in _pending_states:
        logger.warning("oauth_invalid_state", state=state[:8])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state. Possible CSRF attack. Please try logging in again.",
        )
    del _pending_states[state]

    try:
        # Exchange code for tokens
        token_data = await zoho_oauth.exchange_code_for_tokens(code)

        # Get user's Zoho profile and portal ID
        access_token = token_data["access_token"]
        profile = await zoho_oauth.get_zoho_user_profile(access_token)
        portal_id = await zoho_oauth.get_zoho_portal_id(access_token)

        # Store in DB (creates or updates user row)
        user = await zoho_oauth.upsert_user(db, profile, token_data, portal_id)

        # Issue our own JWT to the frontend
        jwt_token = create_access_token(user.id)

        logger.info("oauth_callback_success", user_id=user.id, email=user.email)

    except ValueError as exc:
        logger.error("oauth_callback_failed", error=str(exc))
        return RedirectResponse(
            url=f"{settings.frontend_url}/?error=oauth_failed"
        )
    except Exception as exc:
        logger.error("oauth_callback_unexpected", error=str(exc))
        return RedirectResponse(
            url=f"{settings.frontend_url}/?error=server_error&detail={str(exc)[:120]}"
        )

    # Redirect to frontend chat page — JWT is passed as a URL fragment
    # The frontend reads it from the URL, stores it in localStorage, then removes it from URL
    return RedirectResponse(
        url=f"{settings.frontend_url}/auth/callback#token={jwt_token}"
    )


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_user)) -> UserProfile:
    """
    Returns the currently authenticated user's profile.
    Used by the frontend to verify the JWT is valid on page load.
    """
    return UserProfile(
        id=current_user.id,
        zoho_user_id=current_user.zoho_user_id,
        email=current_user.email,
        display_name=current_user.display_name,
        portal_id=current_user.portal_id,
    )


@router.get("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logs out the current user.
    Since JWTs are stateless, we just tell the frontend to delete its token.
    The token will expire naturally after ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    logger.info("user_logged_out", user_id=current_user.id)
    return {"message": "Logged out successfully. Please clear your local token."}
