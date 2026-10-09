"""Authentication module for the GKP API."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Any, Protocol

import aiohttp
import jwt

from .exceptions import GkpAuthError, GkpConnectionError


class OAuth2Session(Protocol):
    """Protocol for OAuth2 session objects."""

    @property
    def token(self) -> dict[str, Any]:
        """Get the current token."""
        ...

    async def async_ensure_token_valid(self) -> None:
        """Ensure the token is valid."""
        ...


class GkpAuth:
    """Handle authentication for the GKP API."""

    def __init__(self, oauth_session: OAuth2Session) -> None:
        """Initialize authentication."""
        self._oauth_session = oauth_session
        self._lock = asyncio.Lock()

    @staticmethod
    def extract_user_id_from_token(token: str) -> str | None:
        """Extract the user ID (A1) from a JWT access token."""
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
        except jwt.InvalidTokenError:
            return None
        user_id = payload.get("sub")
        return str(user_id) if user_id else None

    async def get_access_token(self) -> str:
        """Get a valid access token."""
        async with self._lock:
            try:
                await self._oauth_session.async_ensure_token_valid()
            except aiohttp.ClientResponseError as err:
                if (
                    HTTPStatus.BAD_REQUEST <= err.status < HTTPStatus.INTERNAL_SERVER_ERROR
                    and err.status != HTTPStatus.TOO_MANY_REQUESTS
                ):
                    raise GkpAuthError(f"Token refresh rejected: {err}") from err
                raise GkpConnectionError(f"Token refresh failed: {err}") from err
            except aiohttp.ClientError as err:
                raise GkpConnectionError(f"Token refresh failed: {err}") from err

            access_token = self._oauth_session.token.get("access_token")
            if not access_token:
                raise GkpAuthError("No access token available in OAuth session")

            return str(access_token)

    async def get_user_id(self) -> str:
        """Get the user ID (A1) of the authenticated user."""
        user_id = self.extract_user_id_from_token(await self.get_access_token())
        if not user_id:
            raise GkpAuthError("Access token does not contain a user ID")
        return user_id
