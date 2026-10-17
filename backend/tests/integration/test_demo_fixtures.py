"""Offline demo mode replays recorded responses with no network (fixtures/demo, made by `make record-fixtures`)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.services import Services
from app.main import create_app

DEMO = Path(__file__).resolve().parents[3] / "fixtures" / "demo"
pytestmark = pytest.mark.skipif(not (DEMO / "manifest.json").exists(), reason="no recordings")


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("DEMO_FIXTURES", "1")
    monkeypatch.setenv("LEAVEBY_FIXTURES_DIR", str(DEMO))
    return TestClient(create_app(Services.create(routing_interval_s=0.0)), raise_server_exceptions=False)


def body(dest: dict) -> dict:
    return {
        "origin": {"label": "Glasgow Central", "lat": 55.8587, "lon": -4.2575},
        "destination": dest,
        "arrive_by": "2026-10-19T09:00:00+01:00",
        "constraints": {"has_car": True},
    }


EDB = {"label": "Edinburgh Waverley", "lat": 55.9521, "lon": -3.1895}


def test_a_demo_route_replays_with_every_provider_badged_recorded(demo):
    r = demo.post("/v1/recommendations", json=body(EDB))
    assert r.status_code == 200
    data, meta = r.json()["data"], r.json()["meta"]
    kinds = {s["id"]: s["kind"] for s in meta["sources"]}
    assert "live" not in kinds.values() and "cached" not in kinds.values()
    assert kinds["open-meteo-ensemble"] == kinds["osrm"] == "recorded"
    assert any(k.startswith("tomtom-") and v == "recorded" for k, v in kinds.items())
    assert data["headline"] is not None and data["route"]["car_line"]


def test_an_unrecorded_route_gets_a_clear_message(demo):
    r = demo.post("/v1/recommendations", json=body({"label": "Dundee", "lat": 56.4691, "lon": -2.9749}))
    assert r.status_code == 422
    assert "Offline demo mode has recordings for these routes only" in r.json()["error"]["detail"]


def test_recorded_place_search_is_badged_recorded(demo):
    r = demo.get("/v1/geocode", params={"q": "Edinburgh", "limit": 6}).json()
    assert r["data"]["places"] and r["meta"]["sources"][0]["kind"] == "recorded"
    assert demo.get("/v1/geocode", params={"q": "Inverness", "limit": 6}).status_code == 422


def test_the_recordings_never_contain_an_api_key():
    for f in DEMO.glob("*.json"):
        text = f.read_text()
        assert "key=" not in text and '"key": "' not in text.replace('"key": "GET ', "")
