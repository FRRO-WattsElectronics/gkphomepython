"""Fixtures for gkphomepython tests."""

from collections.abc import AsyncGenerator

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from gkphomepython import GkpAuth, GkpClient, Installation

from .common import FakeApi, FakeOAuthSession, load_fixture


@pytest.fixture
def oauth_session() -> FakeOAuthSession:
    """Return a fake OAuth2 session."""
    return FakeOAuthSession()


@pytest.fixture
def auth(oauth_session: FakeOAuthSession) -> GkpAuth:
    """Return an auth object."""
    return GkpAuth(oauth_session)


@pytest.fixture
async def api() -> AsyncGenerator[tuple[FakeApi, str]]:
    """Start the fake API and return it with its base URL."""
    fake = FakeApi()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    server = TestServer(app)
    await server.start_server()
    yield fake, str(server.make_url("")).rstrip("/")
    await server.close()


@pytest.fixture
async def session() -> AsyncGenerator[aiohttp.ClientSession]:
    """Return an aiohttp session."""
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def fake_api(api: tuple[FakeApi, str]) -> FakeApi:
    """Return the fake API."""
    return api[0]


@pytest.fixture
def client(
    auth: GkpAuth, session: aiohttp.ClientSession, api: tuple[FakeApi, str]
) -> GkpClient:
    """Return a client pointing to the fake API."""
    return GkpClient(auth, session, base_url=api[1], subscription_key="key", timeout=1)


@pytest.fixture
def installation() -> Installation:
    """Return the installation from the fixture."""
    return Installation.from_dict(load_fixture("installations.json")[0])
