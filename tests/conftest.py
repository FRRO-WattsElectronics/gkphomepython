"""Fixtures for gkphomepython tests."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import jwt
import pytest

from gkphomepython import GkpAuth, GkpClient, Installation

USER_ID = "user-a1"
ACCESS_TOKEN = jwt.encode(
    {"sub": USER_ID}, "secret-key-for-tests-only-32bytes", algorithm="HS256"
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text())


class FakeOAuthSession:
    """OAuth2 session returning a static token."""

    def __init__(self, token: dict[str, Any] | None = None) -> None:
        self.token = token if token is not None else {"access_token": ACCESS_TOKEN}
        self.refresh_error: Exception | None = None
        self.calls = 0

    async def async_ensure_token_valid(self) -> None:
        self.calls += 1
        if self.refresh_error:
            raise self.refresh_error


@dataclass
class FakeResponse:
    """Response served by the fake API."""

    status: int = 200
    body: str = ""
    delay: float = 0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class RecordedRequest:
    """Request received by the fake API."""

    method: str
    path: str
    headers: dict[str, str]
    json: Any


@dataclass
class FakeApi:
    """In-process HTTP server standing in for the GKP APIM."""

    responses: dict[tuple[str, str], list[FakeResponse]] = field(default_factory=dict)
    requests: list[RecordedRequest] = field(default_factory=list)

    def add(
        self,
        method: str,
        path: str,
        payload: Any = None,
        *,
        status: int = 200,
        body: str | None = None,
        delay: float = 0,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Queue a response; the last one queued is repeated."""
        text = body if body is not None else json.dumps(payload) if payload is not None else ""
        self.responses.setdefault((method, path), []).append(
            FakeResponse(status, text, delay, headers or {})
        )

    def sent(self, method: str, path: str) -> list[RecordedRequest]:
        """Return the requests received on a route."""
        return [r for r in self.requests if (r.method, r.path) == (method, path)]

    async def handle(self, request: web.Request) -> web.Response:
        """Serve the queued response for the route."""
        raw = await request.text()
        self.requests.append(
            RecordedRequest(
                request.method,
                request.path,
                dict(request.headers),
                json.loads(raw) if raw else None,
            )
        )
        queue = self.responses.get((request.method, request.path))
        if not queue:
            return web.Response(status=599, text="no mock")
        response = queue.pop(0) if len(queue) > 1 else queue[0]
        if response.delay:
            await asyncio.sleep(response.delay)
        return web.Response(
            status=response.status,
            text=response.body,
            content_type="application/json",
            headers=response.headers,
        )


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
