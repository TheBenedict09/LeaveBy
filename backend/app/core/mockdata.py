"""Clearly labelled MOCK data: fares, emission placeholders and accessibility scores (blueprint 7.1)."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fares(_M):
    train_base_gbp: float
    train_per_km_gbp: float
    drive_per_km_gbp: float


class Access(_M):
    step_free: bool
    effort: float  # 0-1, higher is easier
    luggage_factor: float  # multiplies effort when travelling with luggage


class MockData(_M):
    kind: Literal["mock"]
    note: str
    fares: Fares
    emissions_kg_per_km: dict[str, float]
    accessibility: dict[str, Access]


DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "mock_data.json"


@lru_cache
def load_mock_data(path: str | None = None) -> MockData:
    """Cached and shared: tests that tweak values must use data.model_copy(deep=True)."""
    p = Path(path or os.environ.get("LEAVEBY_MOCK_DATA") or DEFAULT_PATH)
    return MockData.model_validate(json.loads(p.read_text()))
