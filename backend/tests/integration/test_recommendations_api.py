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
    # Glasgow Central to Edinburgh on Monday 19 Oct 2026 is inside the committed real timetable extract
    assert {"open-meteo-ensemble", "osrm", "rdg-timetable", "mock-rail-delays", "mock-fares"} <= ids
    assert "mock-rail" not in ids
    kinds = {s["id"]: s["kind"] for s in meta["sources"]}
    assert kinds["rdg-timetable"] == "static" and kinds["mock-rail-delays"] == "mock"

    assert {o["mode"] for o in data["options"]} == {"walk", "bike", "drive", "train"}
    ranked = [o for o in data["options"] if o["rank"] is not None]
    assert [o["rank"] for o in ranked] == list(range(1, len(ranked) + 1))
    assert all(o["p_on_time"] >= 0.95 for o in ranked)
    assert data["headline"]["mode"] == ranked[0]["mode"]
    assert data["headline"]["total_scenarios"] == 51 * 40
    assert data["explanation"]["because"]
    assert data["hedge"] is not None and data["hedge"]["backup_mode"] != data["headline"]["mode"]

    walk = mode(data, "walk")  # 77 km on foot is beyond the default 1200 m limit
    assert walk["feasible"] is False and walk["infeasible_reason"] == "Further than your walking limit"
    assert walk["rank"] is None and walk["leave_by"] is None
    train = mode(data, "train")
    assert "rdg-timetable" in train["provenance"] and "mock-rail" not in train["provenance"]
    assert all("desnz-ghg-2026" in o["provenance"] and "mock-emissions" not in o["provenance"] for o in data["options"])
    assert kinds["desnz-ghg-2026"] == "static"
    drive = mode(data, "drive")  # official factors: a car emits about 5.4 times more per km than a train
    assert drive["co2e_kg"] / train["co2e_kg"] == pytest.approx(0.16590 / 0.03092, rel=1e-6)
    if train["feasible"]:
        svc = train["service"]
        assert svc["from_station"].startswith("Glasgow") and svc["to_station"] == "Edinburgh"
        assert when(train["leave_by"]) < when(svc["depart_at"]) < when(svc["arrive_at"])  # leave home, board, arrive
    bike = mode(data, "bike")  # 75 km by bike is beyond the default 25 km cycling limit
    assert bike["feasible"] is False and bike["infeasible_reason"] == "Further than your cycling limit"


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
    assert {x["kind"] for x in s} == {"live", "static", "mock"}
    assert any(x["id"] == "rdg-timetable" and "Rail Delivery Group" in x["attribution"] for x in s)
    a = client.get("/v1/assumptions").json()["data"]
    assert a["model"]["rail"]["calm_within_5min_target"] == 0.865 and a["model"]["rail"]["calm_target_sources"]
    assert "placeholder" in a["model"]["status"] and a["mock_data"]["kind"] == "mock"
    assert a["model"]["noise"]["sigma"]["drive"] > 0


# --- TomTom traffic (synthetic responses, fake key, no network) ---------------------------------------------

TOMTOM_ROUTE = {
    "routes": [
        {
            "summary": {"lengthInMeters": 78600, "travelTimeInSeconds": 4800},
            "legs": [{"points": [{"latitude": 55.86, "longitude": -4.26}, {"latitude": 55.95, "longitude": -3.19}]}],
        }
    ]
}
CRASH = {"delay": 540, "events": [{"description": "Crash"}], "from": "M8 J15"}
TOMTOM_INCIDENTS = {"incidents": [{"properties": CRASH}]}


@pytest.fixture
def traffic_client():
    from fastapi.testclient import TestClient

    from app.adapters.tomtom import TrafficAdapter
    from app.api.services import Services
    from app.main import create_app

    services = Services.create(routing_interval_s=0.0)
    services.traffic = TrafficAdapter(services.client, "fake-key")
    return TestClient(create_app(services), raise_server_exceptions=False)


def stub_tomtom(status: int = 200):
    return SimpleNamespace(
        route=respx.get(url__regex=r"https://api\.tomtom\.com/routing/.*").mock(
            return_value=httpx.Response(status, json=TOMTOM_ROUTE if status == 200 else {})
        ),
        incidents=respx.get(url__regex=r"https://api\.tomtom\.com/traffic/.*").mock(
            return_value=httpx.Response(200, json=TOMTOM_INCIDENTS)
        ),
    )


@respx.mock
def test_tomorrow_uses_predicted_traffic_for_the_car_and_no_incidents(traffic_client, valid_request):
    stub()
    tt = stub_tomtom()
    body = traffic_client.post("/v1/recommendations", json=with_car(valid_request)).json()
    traffic = body["data"]["traffic"]
    assert traffic["basis"] == "predicted" and traffic["car_min"] == 80.0 and traffic["incidents"] is None
    assert tt.incidents.call_count == 0  # incidents now say nothing about Monday morning
    drive = mode(body["data"], "drive")
    assert "tomtom-predicted" in drive["provenance"]
    assert {s["id"] for s in body["meta"]["sources"]} >= {"tomtom-predicted"}


@respx.mock
def test_a_trip_leaving_soon_uses_live_traffic_and_reports_incidents(traffic_client, valid_request):
    stub()
    stub_tomtom()
    soon = {**with_car(valid_request), "arrive_by": "2026-10-17T15:00:00+01:00"}  # now is 13:00 BST
    traffic = traffic_client.post("/v1/recommendations", json=soon).json()["data"]["traffic"]
    assert traffic["basis"] == "live"
    assert traffic["incidents"] == {
        "count": 1,
        "worst_delay_min": 9.0,
        "description": "Crash from M8 J15",
        "simulated": False,
    }


@respx.mock
def test_tomtom_failure_falls_back_to_free_flow_with_a_warning(traffic_client, valid_request):
    stub()
    stub_tomtom(status=503)
    body = traffic_client.post("/v1/recommendations", json=with_car(valid_request)).json()
    assert body["ok"] is True and body["data"]["traffic"]["basis"] == "free-flow"
    assert [w["code"] for w in body["meta"]["warnings"]] == ["TRAFFIC_UNAVAILABLE"]
    assert "fake-key" not in str(body)


@respx.mock
def test_without_a_key_the_response_is_unchanged(client, valid_request):
    stub()
    body = client.post("/v1/recommendations", json=with_car(valid_request)).json()
    assert body["data"]["traffic"] is None and not respx.calls.last.request.url.host.endswith("tomtom.com")


@respx.mock
def test_the_demo_accident_is_labelled_simulated_everywhere(client, valid_request):
    stub()
    plain = client.post("/v1/recommendations", json=with_car(valid_request)).json()["data"]
    req = {**with_car(valid_request), "options": {"simulate_incident": True}}
    body = client.post("/v1/recommendations", json=req).json()
    data = body["data"]
    assert data["traffic"]["incidents"]["simulated"] is True and data["traffic"]["basis"] == "free-flow"
    assert "simulated-incident" in mode(data, "drive")["provenance"]
    assert {s["kind"] for s in body["meta"]["sources"] if s["id"] == "simulated-incident"} == {"mock"}
    assert when(mode(data, "drive")["arrival"]["p50"]) > when(mode(plain, "drive")["arrival"]["p50"])
