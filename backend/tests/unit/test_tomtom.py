"""TomTom adapter: parsing, caching and key hygiene. Synthetic payloads, no network, no real key."""

import asyncio

import httpx
import pytest
import respx

from app.adapters.tomtom import TrafficAdapter, bbox_km2, parse_incidents, parse_route
from app.core.resilience import UpstreamError

KEY = "test-key-not-real"
ROUTE = {
    "routes": [
        {
            "summary": {"lengthInMeters": 78600, "travelTimeInSeconds": 4764, "noTrafficTravelTimeInSeconds": 3900},
            "legs": [{"points": [{"latitude": 55.86, "longitude": -4.26}, {"latitude": 55.95, "longitude": -3.19}]}],
        }
    ]
}
INCIDENTS = {
    "incidents": [
        {"properties": {"delay": 120, "events": [{"description": "Queuing traffic"}], "from": "J15", "to": "J16"}},
        {"properties": {"delay": 711, "events": [{"description": "Stationary traffic"}], "from": "M73 J19"}},
        {"properties": {"delay": 0, "events": [{"description": "Roadworks"}]}},  # no delay: not counted
    ]
}


def test_route_parses_time_with_traffic_and_the_route_box():
    r = parse_route(ROUTE, "predicted")
    assert (r.distance_m, r.duration_s, r.no_traffic_s, r.basis) == (78600.0, 4764.0, 3900.0, "predicted")
    assert r.bbox == (-4.26, 55.86, -3.19, 55.95)


def test_malformed_route_is_an_upstream_error():
    with pytest.raises(UpstreamError):
        parse_route({"routes": []}, "live")


def test_incidents_count_only_delays_and_describe_the_worst():
    found = parse_incidents(INCIDENTS)
    assert (found.count, found.worst_delay_s) == (2, 711)
    assert found.description == "Stationary traffic from M73 J19"
    assert parse_incidents({"incidents": []}).count == 0


def test_bbox_area_limits_the_incident_search():
    assert 500 < bbox_km2((-4.30, 55.84, -3.15, 55.97)) < 2000  # Glasgow to Edinburgh
    assert bbox_km2((-4.26, 51.5, -0.12, 55.86)) > 10_000  # Glasgow to London: too big for one request


@respx.mock
def test_predicted_routes_are_cached_per_15_minute_bucket_and_never_leak_the_key():
    routing = respx.get(url__regex=r"https://api\.tomtom\.com/routing/.*")
    calls = routing.mock(return_value=httpx.Response(200, json=ROUTE))

    async def go():
        async with httpx.AsyncClient() as c:
            a = TrafficAdapter(c, KEY)
            first = await a.route((55.8587, -4.2575), (55.9521, -3.1895), 1_792_400_000, live=False)
            again = await a.route((55.8587, -4.2575), (55.9521, -3.1895), 1_792_400_000 + 60, live=False)
            return first, again

    first, again = asyncio.run(go())
    assert calls.call_count == 1 and again.meta.kind == "cached"
    assert first.meta.id == "tomtom-predicted" and first.data.basis == "predicted"
    assert "departAt=2026" in str(calls.calls[0].request.url)  # the departure time is sent
    assert KEY not in first.meta.model_dump_json()


@respx.mock
def test_errors_do_not_include_the_key():
    respx.get(url__regex=r"https://api\.tomtom\.com/.*").mock(return_value=httpx.Response(403))

    async def go():
        async with httpx.AsyncClient() as c:
            await TrafficAdapter(c, KEY).route((55.8, -4.2), (55.9, -3.1), 0, live=True)

    with pytest.raises(UpstreamError) as e:
        asyncio.run(go())
    assert KEY not in str(e.value)
