"""Shared wrapper for every live adapter (blueprint 7.3): timeout, bounded retries with
backoff + jitter on timeouts/5xx only, and a single error type for callers to handle."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx


class UpstreamError(Exception):
    """A provider could not give us usable data (network, 5xx, 4xx, or malformed body)."""


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retries: int = 2,
    backoff_s: float = 0.25,
    timeout_s: float = 3.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Any:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = await client.get(url, params=params, headers=headers, timeout=timeout_s)
            if r.status_code >= 500:
                raise UpstreamError(f"{url} returned {r.status_code}")
            if r.status_code >= 400:
                # Our request is wrong or we are rate limited: retrying will not help.
                raise UpstreamError(f"{url} returned {r.status_code}")
            try:
                return r.json()
            except ValueError as e:
                raise UpstreamError(f"{url} returned invalid JSON") from e
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = UpstreamError(f"{url} unreachable: {type(e).__name__}")
        except UpstreamError as e:
            if "returned 4" in str(e) or "invalid JSON" in str(e):
                raise
            last = e
        if attempt < retries:
            await sleep(backoff_s * (2**attempt) * (0.5 + random.random()))
    assert last is not None
    raise last
