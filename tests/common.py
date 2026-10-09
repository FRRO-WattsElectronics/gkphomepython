"""Shared helpers for gkphomepython tests."""

import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from aiohttp import web
import jwt

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
