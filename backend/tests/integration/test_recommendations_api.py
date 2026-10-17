"""Full requests through the real app. Providers are stubbed at the HTTP boundary with the REAL recorded
responses in fixtures/raw/, so the adapters, decision layer and envelope are all exercised for real."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

RAW = Path(__file__).resolve().parents[3] / "fixtures" / "raw"
pytestmark = pytest.mark.skipif(not (RAW / "weather_glasgow.json").exists(), reason="needs recorded provider responses")

WEATHER = r"https://ensemble-api\.open-meteo\.com/.*"
GEOCODE = r"https://geocoding-api\.open-meteo\.com/.*"


def _resp(status: int, fixture: str) -> httpx.Response:
    return httpx.Response(status, content=(RAW / fixture).read_bytes() if status == 200 else b"")


def stub(weather: int = 200, routes: int = 200, geocode: int = 200) -> SimpleNamespace:
    """Register fake providers; returns the respx routes so tests can count calls."""
    return SimpleNamespace(
        weather=respx.get(url__regex=WEATHER).mock(return_value=_resp(weather, "weather_glasgow.json")),
        routing=[
            respx.get(url__regex=rf"https://routing\.openstreetmap\.de/routed-{p}/.*").mock(
                return_value=_resp(routes, f"route_{p}.json")
            )
            for p in ("car", "bike", "foot")
        ],
        geocode=respx.get(url__regex=GEOCODE).mock(return_value=_resp(geocode, "geocode_edinburgh.json")),
    )


def with_car(req):
    return {**req, "constraints": {"has_car": True}}


def mode(data, name):
    return next(o for o in data["options"] if o["mode"] == name)


def when(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


@respx.mock
def test_happy_path_returns_a_ranked_decision_with_provenance(client, valid_request):
    stub()
    r = client.post("/v1/recommendations", json=with_car(valid_request))
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    data, meta = body["data"], body["meta"]

    assert meta["degraded"] is False and meta["warnings"] == []
    ids = {s["id"] for s in meta["sources"]}
    assert {"open-meteo-ensemble", "osrm", "mock-rail", "mock-fares"} <= ids
    assert {s["kind"] for s in meta["sources"] if s["id"] == "mock-rail"} == {"mock"}

    assert {o["mode"] for o in data["options"]} == {"walk", "bike", "drive", "train"}
    ranked = [o for o in data["options"] if o["rank"] is not None]
    assert [o["rank"] for o in ranked] == list(range(1, len(ranked) + 1))
    assert all(o["p_on_time"] >= 0.95 for o in ranked)
    assert data["headline"]["mode"] == ranked[0]["mode"]
    assert data["headline"]["total_scenarios"] == 51
    assert data["explanation"]["because"]
    assert data["hedge"] is not None and data["hedge"]["backup_mode"] != data["headline"]["mode"]

    walk = mode(data, "walk")  # 77 km on foot is beyond the default 1200 m limit
    assert walk["feasible"] is False and walk["infeasible_reason"] == "Further than your walking limit"
    assert walk["rank"] is None and walk["leave_by"] is None


@respx.mock
def test_without_a_car_driving_is_unavailable_but_still_listed(client, valid_request):
    stub()
    data = client.post("/v1/recommendations", json=valid_request).json()["data"]
    drive = mode(data, "drive")
    assert drive["feasible"] is False and drive["infeasible_reason"] == "No car available"


@respx.mock
def test_weather_outage_degrades_loudly_but_still_answers(client, valid_request):
    stub(weather=500)
    r = client.post("/v1/recommendations", json=with_car(valid_request))
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["meta"]["degraded"] is True
    assert "WEATHER_UNAVAILABLE" in {w["code"] for w in body["meta"]["warnings"]}
    kinds = {s["id"]: s["kind"] for s in body["meta"]["sources"]}
    assert kinds["no-weather"] == "estimated" and "open-meteo-ensemble" not in kinds
    assert body["data"]["headline"] is not None


@respx.mock
def test_routing_outage_uses_flagged_estimates(client, valid_request):
    stub(routes=500)
    body = client.post("/v1/recommendations", json=with_car(valid_request)).json()
    assert body["ok"] is True and body["meta"]["degraded"] is True
    assert "ROUTE_ESTIMATED" in {w["code"] for w in body["meta"]["warnings"]}
    assert {s["id"] for s in body["meta"]["sources"]} >= {"osrm-estimate"}


@respx.mock
def test_everything_down_is_a_502_envelope_not_a_crash(client, valid_request):
    stub(weather=500, routes=500)
    r = client.post("/v1/recommendations", json=valid_request)
    body = r.json()
    assert r.status_code == 502 and body["ok"] is False
    assert body["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert "Traceback" not in r.text


@respx.mock
def test_same_request_gives_the_same_seed_and_answer(client, valid_request):
    stub()
    a = client.post("/v1/recommendations", json=with_car(valid_request)).json()
    b = client.post("/v1/recommendations", json=with_car(valid_request)).json()
    assert a["meta"]["seed"] == b["meta"]["seed"]
    assert a["data"]["headline"] == b["data"]["headline"]
    assert a["data"]["recommendation_id"] != b["data"]["recommendation_id"]


@respx.mock
def test_rescore_answers_from_the_stored_simulation_without_calling_providers(client, valid_request):
    routes = stub()
    first = client.post("/v1/recommendations", json=with_car(valid_request)).json()["data"]
    calls = (routes.weather.call_count, [r.call_count for r in routes.routing])

    r = client.post(f"/v1/recommendations/{first['recommendation_id']}/rescore", json={"confidence": 0.8})
    second = r.json()["data"]
    assert r.status_code == 200 and second["recommendation_id"] == first["recommendation_id"]
    assert (routes.weather.call_count, [x.call_count for x in routes.routing]) == calls  # nothing refetched

    for a in first["options"]:
        b = mode(second, a["mode"])
        if a["leave_by"] and b["leave_by"]:
            assert when(b["leave_by"]) >= when(a["leave_by"])  # less certainty means you can leave later


@respx.mock
def test_rescore_priorities_can_change_the_winner(client, valid_request):
    stub()
    first = client.post("/v1/recommendations", json=with_car(valid_request)).json()["data"]
    greenest = {"weights": {"time": 0, "cost": 0, "carbon": 1, "accessibility": 0}}
    second = client.post(f"/v1/recommendations/{first['recommendation_id']}/rescore", json=greenest).json()["data"]
    assert second["headline"]["mode"] in {"bike", "walk", "train"}  # never the highest-carbon option, drive
    assert second["headline"]["mode"] != "drive"


def test_rescore_unknown_id_is_a_404_envelope(client):
    r = client.post("/v1/recommendations/rec_nope/rescore", json={"confidence": 0.9})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


@respx.mock
def test_rescore_validates_input(client, valid_request):
    stub()
    rid = client.post("/v1/recommendations", json=valid_request).json()["data"]["recommendation_id"]
    r = client.post(f"/v1/recommendations/{rid}/rescore", json={"confidence": 1.0})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


@respx.mock
def test_calendar_download_has_a_leave_by_alarm(client, valid_request):
    stub()
    rid = client.post("/v1/recommendations", json=with_car(valid_request)).json()["data"]["recommendation_id"]
    r = client.get(f"/v1/recommendations/{rid}/calendar.ics", params={"mode": "train"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    for needle in ("BEGIN:VCALENDAR", "BEGIN:VEVENT", "BEGIN:VALARM", "END:VCALENDAR"):
        assert needle in r.text
    assert client.get(f"/v1/recommendations/{rid}/calendar.ics", params={"mode": "walk"}).status_code == 404


@respx.mock
def test_geocode_live(client):
    stub()
    live = client.get("/v1/geocode", params={"q": "Edinburgh"}).json()
    assert live["ok"] and live["data"]["places"] and live["meta"]["degraded"] is False
    assert live["meta"]["sources"][0]["id"] == "open-meteo-geocoding"


@respx.mock
def test_geocode_falls_back_to_the_builtin_city_list(client):
    stub(geocode=500)
    fallback = client.get("/v1/geocode", params={"q": "glas"}).json()
    assert fallback["meta"]["degraded"] is True
    assert "Glasgow" in fallback["data"]["places"][0]["label"]
    assert fallback["meta"]["sources"][0]["kind"] == "estimated"


def test_geocode_rejects_bad_input(client):
    assert client.get("/v1/geocode", params={"q": "x"}).status_code == 422
    assert client.get("/v1/geocode", params={"q": "a" * 101}).status_code == 422


def test_sources_and_assumptions_are_public(client):
    s = client.get("/v1/sources").json()["data"]["sources"]
    assert {x["kind"] for x in s} == {"live", "mock"}
    a = client.get("/v1/assumptions").json()["data"]
    assert "placeholder" in a["model"]["status"] and a["mock_data"]["kind"] == "mock"
    assert a["model"]["noise"]["sigma"]["drive"] > 0
