"""Tests for gkphomepython authentication."""

import aiohttp
import jwt
from multidict import CIMultiDict, CIMultiDictProxy
import pytest
from yarl import URL

from gkphomepython import GkpAuth, GkpAuthError, GkpConnectionError

from .conftest import ACCESS_TOKEN, USER_ID, FakeOAuthSession


def test_extract_user_id_from_token() -> None:
    """Test extracting the user ID from a JWT."""
    assert GkpAuth.extract_user_id_from_token(ACCESS_TOKEN) == USER_ID


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="invalid"),
        pytest.param(
            jwt.encode({"name": "x"}, "secret-key-for-tests-only-32bytes", algorithm="HS256"),
            id="no_sub",
        ),
    ],
)
def test_extract_user_id_invalid(token: str) -> None:
    """Test invalid tokens return None."""
    assert GkpAuth.extract_user_id_from_token(token) is None


async def test_get_access_token(auth: GkpAuth, oauth_session: FakeOAuthSession) -> None:
    """Test the token is refreshed then returned."""
    assert await auth.get_access_token() == ACCESS_TOKEN
    assert await auth.get_user_id() == USER_ID
    assert oauth_session.calls == 2


async def test_missing_access_token() -> None:
    """Test a session without access token."""
    auth = GkpAuth(FakeOAuthSession({}))

    with pytest.raises(GkpAuthError):
        await auth.get_access_token()


async def test_token_without_user_id() -> None:
    """Test a token without subject claim."""
    auth = GkpAuth(FakeOAuthSession({"access_token": "not-a-jwt"}))

    with pytest.raises(GkpAuthError):
        await auth.get_user_id()


def _response_error(status: int) -> aiohttp.ClientResponseError:
    request_info = aiohttp.RequestInfo(
        URL("https://gkp.example/connect/token"), "POST", CIMultiDictProxy(CIMultiDict())
    )
    return aiohttp.ClientResponseError(request_info, (), status=status)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(_response_error(400), GkpAuthError, id="rejected"),
        pytest.param(_response_error(401), GkpAuthError, id="unauthorized"),
        pytest.param(_response_error(429), GkpConnectionError, id="rate_limited"),
        pytest.param(_response_error(503), GkpConnectionError, id="server_error"),
        pytest.param(aiohttp.ClientConnectionError(), GkpConnectionError, id="network"),
    ],
)
async def test_refresh_errors(
    auth: GkpAuth,
    oauth_session: FakeOAuthSession,
    error: Exception,
    expected: type[Exception],
) -> None:
    """Test token refresh errors are mapped."""
    oauth_session.refresh_error = error

    with pytest.raises(expected):
        await auth.get_access_token()
