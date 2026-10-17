from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import envelope


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_validation_error_uses_envelope(client, valid_request):
    valid_request["arrive_by"] = "2026-12-25T09:00:00+00:00"
    r = client.post("/v1/recommendations", json=valid_request)
    body = r.json()
    assert r.status_code == 422
    assert body["ok"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["fields"][0]["path"] == "arrive_by"
    assert "7 days" in body["error"]["detail"]
    assert body["meta"]["request_id"].startswith("req_")


def test_not_found_uses_envelope(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_unhandled_exception_hides_stack_trace():
    app = FastAPI()
    envelope.install(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internals")

    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL"
    assert "secret" not in r.text
