from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core import clock
from app.main import app

FIXED_NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: FIXED_NOW)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def valid_request():
    return {
        "origin": {"label": "Glasgow Central", "lat": 55.8587, "lon": -4.2575},
        "destination": {"label": "Edinburgh Waverley", "lat": 55.9521, "lon": -3.1895},
        "arrive_by": "2026-10-19T09:00:00+01:00",
        "confidence": 0.95,
    }
