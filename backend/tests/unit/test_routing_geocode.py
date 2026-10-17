import json
from pathlib import Path

import pytest

from app.adapters.geocode import parse_places
from app.adapters.routing import bearing, parse_route
from app.core.resilience import UpstreamError

RAW = Path(__file__).resolve().parents[3] / "fixtures" / "raw"


def ok_payload():
    return {
        "code": "Ok",
        "routes": [
            {"distance": 1000.0, "duration": 120.0, "geometry": {"coordinates": [[-4.25, 55.86], [-3.19, 55.95]]}}
        ],
    }


def test_parse_route():
    r = parse_route("car", ok_payload())
    assert (r.distance_m, r.duration_s) == (1000.0, 120.0)
    assert 70 < r.bearing_deg < 90  # Glasgow -> Edinburgh is almost due east


def test_bearing_cardinals():
    assert bearing(0, 0, 0, 1) == pytest.approx(0)
    assert bearing(0, 0, 1, 0) == pytest.approx(90)
    assert bearing(0, 0, 0, -1) == pytest.approx(180)


@pytest.mark.parametrize("bad", [{}, {"code": "NoRoute"}, {"code": "Ok", "routes": []}, {"code": "Ok", "routes": [{}]}])
def test_bad_route_payloads(bad):
    with pytest.raises(UpstreamError):
        parse_route("car", bad)


def test_geocode_parse_and_empty():
    p = {
        "results": [
            {
                "name": "Edinburgh",
                "admin1": "Scotland",
                "country": "United Kingdom",
                "latitude": 55.95,
                "longitude": -3.2,
            },
            {"bad": 1},
        ]
    }
    places = parse_places(p)
    assert len(places) == 1 and places[0].label == "Edinburgh, Scotland, United Kingdom"
    assert parse_places({}) == []  # no match is not an error


@pytest.mark.parametrize(
    "name,profile", [("route_car.json", "car"), ("route_bike.json", "bike"), ("route_foot.json", "foot")]
)
def test_real_routes_parse(name, profile):
    f = RAW / name
    if not f.exists():
        pytest.skip("put the real curl output in fixtures/raw/")
    assert parse_route(profile, json.loads(f.read_text())).duration_s > 0
