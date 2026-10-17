import os

os.environ["TOMTOM_API_KEY"] = ""  # tests never call TomTom; set before the app (and its .env loader) is imported

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.services import Services
from app.core import clock, resilience
from app.main import create_app

FIXED_NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: FIXED_NOW)


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch):
    monkeypatch.setattr(resilience, "DEFAULT_BACKOFF_S", 0.0)


@pytest.fixture
def client():
    """A fresh app per test (fresh caches), with the routing throttle off so tests are quick."""
    app = create_app(Services.create(routing_interval_s=0.0))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def valid_request():
    return {
        "origin": {"label": "Glasgow Central", "lat": 55.8587, "lon": -4.2575},
        "destination": {"label": "Edinburgh Waverley", "lat": 55.9521, "lon": -3.1895},
        "arrive_by": "2026-10-19T09:00:00+01:00",
        "confidence": 0.95,
    }
