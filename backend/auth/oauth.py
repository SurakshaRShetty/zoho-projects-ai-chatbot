"""
ZohoOAuthClient — handles the full OAuth 2.0 Authorization Code flow.

Responsibilities:
  - Build the Zoho consent URL
  - Exchange auth code for tokens
  - Refresh expired access tokens
  - Encrypt tokens before DB storage
  - Fetch Zoho profile + portal ID
"""

from datetime import UTC, datetime, timedelta

import httpx
import structlog
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.db import User

logger = structlog.get_logger()

ZOHO_SCOPES = ",".join([
    "ZohoProjects.portals.READ",
    "ZohoProjects.projects.ALL",
    "ZohoProjects.tasks.ALL",
    "ZohoProjects.users.READ",
    "AaaServer.profile.Read",
])


class ZohoOAuthClient:

    def __init__(self) -> None:
        self._fernet = Fernet(settings.encryption_key.encode())

    # ─────────────────────────────────────────────
    # Encryption helpers
    # ─────────────────────────────────────────────

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()

    # ─────────────────────────────────────────────
    # Authorization URL
    # ─────────────────────────────────────────────

    def get_authorization_url(self, state: str) -> str:

        params = {
            "client_id": settings.zoho_client_id,
            "response_type": "code",
            "redirect_uri": settings.zoho_redirect_uri,
            "scope": ZOHO_SCOPES,
            "access_type": "offline",
            "state": state,
            "prompt": "consent",
        }

        query = "&".join(f"{k}={v}" for k, v in params.items())

        return f"{settings.zoho_accounts_url}/oauth/v2/auth?{query}"

    # ─────────────────────────────────────────────
    # Exchange code for tokens
    # ─────────────────────────────────────────────

    async def exchange_code_for_tokens(self, code: str) -> dict:

        async with httpx.AsyncClient() as client:

            response = await client.post(
                f"{settings.zoho_accounts_url}/oauth/v2/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.zoho_client_id,
                    "client_secret": settings.zoho_client_secret,
                    "redirect_uri": settings.zoho_redirect_uri,
                    "code": code,
                },
            )

            response.raise_for_status()

            data = response.json()

        if "error" in data:
            raise ValueError(f"Zoho token exchange failed: {data['error']}")

        logger.info(
            "zoho_token_exchanged",
            has_refresh=bool(data.get("refresh_token"))
        )

        return data

    # ─────────────────────────────────────────────
    # Refresh token
    # ─────────────────────────────────────────────

    async def refresh_access_token(self, refresh_token: str) -> dict:

        async with httpx.AsyncClient() as client:

            response = await client.post(
                f"{settings.zoho_accounts_url}/oauth/v2/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.zoho_client_id,
                    "client_secret": settings.zoho_client_secret,
                    "refresh_token": refresh_token,
                },
            )

            response.raise_for_status()

            data = response.json()

        if "error" in data:
            raise ValueError(f"Zoho token refresh failed: {data['error']}")

        logger.info("zoho_token_refreshed")

        return data

    # ─────────────────────────────────────────────
    # User profile
    # ─────────────────────────────────────────────

    async def get_zoho_user_profile(self, access_token: str) -> dict:

        url = f"{settings.zoho_accounts_url}/oauth/user/info"

        headers_to_try = [
            f"Bearer {access_token}",
            f"Zoho-oauthtoken {access_token}",
        ]

        for auth_header in headers_to_try:

            try:

                async with httpx.AsyncClient() as client:

                    response = await client.get(
                        url,
                        headers={
                            "Authorization": auth_header
                        }
                    )

                if response.is_success:

                    data = response.json()

                    logger.info(
                        "user_profile_fetched",
                        source="user_info_endpoint"
                    )

                    return {
                        "zoho_user_id": str(
                            data.get("ZUID") or data.get("id", "")
                        ),
                        "email": data.get("Email", ""),
                        "display_name": (
                            f"{data.get('First_Name', '')} "
                            f"{data.get('Last_Name', '')}"
                        ).strip(),
                    }

                logger.warning(
                    "user_info_attempt_failed",
                    status=response.status_code,
                    header_type=auth_header.split()[0]
                )

            except Exception as exc:

                logger.warning(
                    "user_info_request_error",
                    error=str(exc)
                )

        logger.info(
            "user_profile_fallback",
            source="portals_api"
        )

        return await self._get_profile_from_portals(access_token)

    # ─────────────────────────────────────────────
    # Fetch portals
    # ─────────────────────────────────────────────

    async def _fetch_portals(self, access_token: str) -> list[dict]:

        url = "https://projectsapi.zoho.in/api/v3/portals"

        headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}"
        }

        async with httpx.AsyncClient() as client:

            response = await client.get(
                url,
                headers=headers
            )

        if not response.is_success:
            logger.error(
                "portal_fetch_failed",
                status=response.status_code,
                body=response.text,
            )
            response.raise_for_status()

        data = response.json()

        # v3 API returns a direct list; v2 returns {"portals": [...]}
        if isinstance(data, list):
            portals = data
        elif isinstance(data, dict):
            if "error" in data:
                logger.error(
                    "portal_fetch_error_response",
                    code=data["error"].get("code"),
                    message=data["error"].get("message"),
                )
                raise ValueError(
                    f"Zoho portals API error: {data['error']}"
                )
            portals = data.get("portals", [])
        else:
            portals = []

        logger.info(
            "portals_fetched",
            count=len(portals)
        )

        return portals

    # ─────────────────────────────────────────────
    # Fallback profile
    # ─────────────────────────────────────────────

    async def _get_profile_from_portals(
        self,
        access_token: str
    ) -> dict:

        try:

            portals = await self._fetch_portals(access_token)

            if portals:

                p = portals[0]

                login_id = p.get("login_id", "")

                owner_id = str(
                    p.get("owner_id", "")
                )

                display_name = (
                    login_id.split("@")[0]
                    if login_id else ""
                )

                logger.info(
                    "user_profile_fetched",
                    source="portals_fallback"
                )

                return {
                    "zoho_user_id": owner_id,
                    "email": login_id,
                    "display_name": display_name,
                }

        except Exception as exc:

            logger.error(
                "profile_fallback_failed",
                error=str(exc)
            )

        raise ValueError(
            "Unable to fetch user profile from Zoho."
        )

    # ─────────────────────────────────────────────
    # Get portal ID
    # ─────────────────────────────────────────────

    async def get_zoho_portal_id(
        self,
        access_token: str
    ) -> str | None:

        try:

            portals = await self._fetch_portals(access_token)

            if not portals:

                logger.warning(
                    "no_zoho_portals_found"
                )

                return None

            portal_id = str(
                portals[0].get("id", "")
            )

            logger.info(
                "zoho_portal_id_saved",
                portal_id=portal_id
            )

            return portal_id

        except Exception as e:

            logger.error(
                "portal_fetch_failed",
                error=str(e)
            )

            return None

    # ─────────────────────────────────────────────
    # Upsert user
    # ─────────────────────────────────────────────

    async def upsert_user(
        self,
        db: AsyncSession,
        profile: dict,
        token_data: dict,
        portal_id: str | None,
    ) -> User:

        expires_in = int(
            token_data.get("expires_in", 3600)
        )

        expires_at = (
            datetime.now(UTC)
            + timedelta(seconds=expires_in - 60)
        )

        result = await db.execute(
            select(User).where(
                User.zoho_user_id
                == profile["zoho_user_id"]
            )
        )

        user = result.scalar_one_or_none()

        refresh_token = token_data.get(
            "refresh_token",
            ""
        )

        if user is None:

            user = User(
                zoho_user_id=profile["zoho_user_id"],
                email=profile["email"],
                display_name=profile["display_name"],
                access_token_encrypted=self.encrypt(
                    token_data["access_token"]
                ),
                refresh_token_encrypted=self.encrypt(
                    refresh_token
                ),
                token_expires_at=expires_at,
                portal_id=portal_id,
            )

            db.add(user)

        else:

            user.email = profile["email"]

            user.display_name = profile["display_name"]

            user.access_token_encrypted = self.encrypt(
                token_data["access_token"]
            )

            if token_data.get("refresh_token"):

                user.refresh_token_encrypted = self.encrypt(
                    token_data["refresh_token"]
                )

            user.token_expires_at = expires_at

            if portal_id:
                user.portal_id = portal_id

        await db.commit()

        await db.refresh(user)

        logger.info(
            "user_upserted",
            user_id=user.id,
            email=user.email
        )

        return user

    # ─────────────────────────────────────────────
    # Get valid token
    # ─────────────────────────────────────────────

    async def get_valid_access_token(
        self,
        db: AsyncSession,
        user: User
    ) -> str:

        now = datetime.now(UTC)

        expires_at = user.token_expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(
                tzinfo=UTC
            )

        if now >= expires_at:

            logger.info(
                "token_expired_refreshing",
                user_id=user.id
            )

            refresh_token = self.decrypt(
                user.refresh_token_encrypted
            )

            new_token_data = (
                await self.refresh_access_token(
                    refresh_token
                )
            )

            expires_in = int(
                new_token_data.get(
                    "expires_in",
                    3600
                )
            )

            user.access_token_encrypted = self.encrypt(
                new_token_data["access_token"]
            )

            user.token_expires_at = (
                now + timedelta(seconds=expires_in - 60)
            )

            await db.commit()

            await db.refresh(user)

        return self.decrypt(
            user.access_token_encrypted
        )


zoho_oauth = ZohoOAuthClient()