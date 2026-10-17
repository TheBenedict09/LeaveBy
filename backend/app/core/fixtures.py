"""Offline demo mode: record upstream HTTP responses once, then replay them with no network.

Recording and replay happen at the HTTP layer (an httpx transport), so the adapters and the decision layer run
exactly as they do live. Requests are keyed by host, path and query parameters, without the API key (never
stored) and without TomTom's departure time (so any demo date replays the recorded traffic). Replayed weather is
shifted by whole days so the recorded forecast covers the days being planned."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "demo"
DROPPED = {"key", "departAt"}  # never stored, and not part of the match
WEATHER_HOST = "ensemble-api.open-meteo.com"
DEMO_ROUTES = "Glasgow Central to Edinburgh Waverley, and Glasgow Central to Paisley Gilmour Street"


class FixtureMiss(Exception):
    """Demo mode was asked for something that was not recorded."""


def demo_dir() -> Path | None:
    """The recordings folder when DEMO_FIXTURES=1, else None."""
    if os.environ.get("DEMO_FIXTURES") != "1":
        return None
    return Path(os.environ.get("LEAVEBY_FIXTURES_DIR") or DEFAULT_DIR)


def request_key(request: httpx.Request) -> str:
    params = sorted((k, v) for k, v in request.url.params.multi_items() if k not in DROPPED)
    return f"{request.method} {request.url.host}{request.url.path}?" + "&".join(f"{k}={v}" for k, v in params)


def _file(root: Path, key: str) -> Path:
    return root / f"{hashlib.sha256(key.encode()).hexdigest()[:20]}.json"


class RecordingTransport(httpx.AsyncBaseTransport):
    """Passes requests to the network and saves every successful JSON response under its key."""

    def __init__(self, root: Path) -> None:
        self._root, self._inner = root, httpx.AsyncHTTPTransport()
        root.mkdir(parents=True, exist_ok=True)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        body = await response.aread()
        if response.status_code == 200:
            key = request_key(request)
            _file(self._root, key).write_text(json.dumps({"key": key, "body": json.loads(body)}))
        # body is already decoded, so the encoding headers must not travel with it
        drop = ("content-encoding", "content-length")
        headers = [(k, v) for k, v in response.headers.items() if k.lower() not in drop]
        return httpx.Response(response.status_code, headers=headers, content=body, request=request)


class FixtureTransport(httpx.AsyncBaseTransport):
    """Serves recorded responses; anything not recorded raises FixtureMiss."""

    def __init__(self, root: Path) -> None:
        self._root = root
        manifest = json.loads((root / "manifest.json").read_text())
        self.recorded_at = datetime.fromisoformat(manifest["recorded_at"])

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        f = _file(self._root, request_key(request))
        if not f.exists():
            raise FixtureMiss(f"Offline demo mode has recordings for these routes only: {DEMO_ROUTES}.")
        body: Any = json.loads(f.read_text())["body"]
        if request.url.host == WEATHER_HOST:
            body = _shift_days(body, self.recorded_at)
        return httpx.Response(200, json=body, request=request)


def _shift_days(payload: dict[str, Any], recorded_at: datetime) -> dict[str, Any]:
    """Move the forecast's timestamps forward by whole days since recording, keeping the hours of day."""
    days = (datetime.now(UTC).date() - recorded_at.date()).days
    hourly = payload.get("hourly") or {}
    if days > 0 and "time" in hourly:
        hourly = {**hourly, "time": [t + days * 86400 for t in hourly["time"]]}
        payload = {**payload, "hourly": hourly}
    return payload
