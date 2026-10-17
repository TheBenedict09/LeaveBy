"""The real GB rail timetable extract (data/rail_timetable.json, built by `make rail-data`). Optional: without
the file every train is simulated, as before."""

import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class _T(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Station(_T):
    name: str
    lat: float
    lon: float


class RailTimetable(_T):
    source: str  # attribution text, shown in the sources panel
    release: str  # feed release tag
    valid_from: date
    valid_to: date
    reference_dates: dict[str, date]
    stations: dict[str, Station]  # keyed by CRS code
    # 'GLC-EDB' -> day type -> [[dep_min, arr_min, operator, headsign], ...], minutes after local midnight
    pairs: dict[str, dict[str, list[tuple[int, int, str, str]]]]


DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "rail_timetable.json"


@lru_cache
def load_timetable(path: str | None = None) -> RailTimetable | None:
    p = Path(path or os.environ.get("LEAVEBY_RAIL_TIMETABLE") or DEFAULT_PATH)
    return RailTimetable.model_validate(json.loads(p.read_text())) if p.exists() else None
