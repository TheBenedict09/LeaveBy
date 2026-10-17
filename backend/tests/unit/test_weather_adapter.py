import asyncio
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
import respx

from app.adapters.weather import URL, WeatherAdapter, parse_ensemble
from app.core.resilience import UpstreamError

ROOT = Path(__file__).resolve().parents[3]
REAL = ROOT / "fixtures" / "raw" / "weather_glasgow.json"


def payload(n_hours=3):
    t = [1_792_000_000 + 3600 * i for i in range(n_hours)]
    h = {"time": t}
    for var in ["precipitation", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "temperature_2m"]:
        h[var] = [0.0] * n_hours  # control member
        h[f"{var}_member01"] = [1.0, None, 2.0][:n_hours]
        h[f"{var}_member02"] = [0.5] * n_hours
    return {"latitude": 55.86, "longitude": -4.26, "utc_offset_seconds": 0, "hourly": h}  # no visibility at all


def test_parse_shapes_and_nulls():
    w = parse_ensemble(payload())
    assert w.n_members == 3
    assert w.precip_mm_h.shape == (3, 3)
    assert np.isnan(w.precip_mm_h[1, 1])  # null -> NaN, no exception
    assert np.isnan(w.visibility_m).all()  # missing variable -> unknown, not a crash
    assert w.times.dtype == np.int64


def test_parse_iso_times_respects_offset():
    p = payload()
    p["hourly"]["time"] = ["2026-10-17T12:00", "2026-10-17T13:00", "2026-10-17T14:00"]
    p["utc_offset_seconds"] = 3600  # BST
    w = parse_ensemble(p)
    assert w.times[0] == 1792234800  # 12:00 BST is 11:00 UTC
    assert w.times[1] - w.times[0] == 3600


@pytest.mark.parametrize("bad", [{}, {"hourly": {}}, {"hourly": {"time": [1]}}, {"hourly": "x"}])
def test_malformed_payload_raises_upstream_error_only(bad):
    with pytest.raises(UpstreamError):
        parse_ensemble(bad)


def test_ragged_series_rejected():
    p = payload()
    p["hourly"]["precipitation_member01"] = [1.0]
    with pytest.raises(UpstreamError):
        parse_ensemble(p)


@pytest.mark.skipif(not REAL.exists(), reason="put the real curl output at fixtures/raw/weather_glasgow.json")
def test_real_payload_parses():
    w = parse_ensemble(json.loads(REAL.read_text()))
    assert w.n_members == 51
    assert w.precip_mm_h.shape[1] == len(w.times)


@respx.mock
def test_live_then_cached_fallback_when_provider_dies():
    async def scenario():
        async with httpx.AsyncClient() as c:
            a = WeatherAdapter(c)
            first = await a.fetch(55.86, -4.26)
            a._cache.ttl_s = -1  # force "not fresh" so the next call tries live
            respx.get(URL).mock(return_value=httpx.Response(500))
            second = await a.fetch(55.86, -4.26)
            return first, second

    respx.get(URL).mock(return_value=httpx.Response(200, json=payload()))
    first, second = asyncio.run(scenario())
    assert first.meta.kind == "live"
    assert second.meta.kind == "cached"  # never silently stale: flagged
    assert second.data is first.data


@respx.mock
def test_no_cache_and_provider_down_raises():
    respx.get(URL).mock(return_value=httpx.Response(500))

    async def scenario():
        async with httpx.AsyncClient() as c:
            return await WeatherAdapter(c).fetch(55.86, -4.26)

    with pytest.raises(UpstreamError):
        asyncio.run(scenario())
