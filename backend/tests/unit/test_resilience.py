import asyncio

import httpx
import pytest
import respx

from app.core.cache import TTLCache
from app.core.resilience import UpstreamError, get_json

URL = "https://example.test/x"


async def _no_sleep(_: float) -> None:
    return None


def run(coro):
    return asyncio.run(coro)


async def _get(**kw):
    async with httpx.AsyncClient() as c:
        return await get_json(c, URL, sleep=_no_sleep, **kw)


@respx.mock
def test_retries_5xx_then_succeeds():
    route = respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    assert run(_get()) == {"ok": 1}
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_retries():
    route = respx.get(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(UpstreamError):
        run(_get(retries=2))
    assert route.call_count == 3


@respx.mock
def test_does_not_retry_4xx():
    route = respx.get(URL).mock(return_value=httpx.Response(429))
    with pytest.raises(UpstreamError):
        run(_get())
    assert route.call_count == 1


@respx.mock
def test_timeout_is_retried_and_wrapped():
    route = respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(UpstreamError):
        run(_get(retries=1))
    assert route.call_count == 2


@respx.mock
def test_invalid_json_is_upstream_error():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(UpstreamError):
        run(_get())


def test_cache_fresh_vs_stale():
    t = [0.0]
    c: TTLCache[str] = TTLCache(ttl_s=10, clock=lambda: t[0])
    c.put("k", "v")
    t[0] = 5
    assert c.get("k") == ("v", 5)
    t[0] = 20
    assert c.get("k") is None  # past ttl
    assert c.get("k", max_age_s=60) == ("v", 20)  # but usable as last-good
    assert c.get("k", max_age_s=10) is None
