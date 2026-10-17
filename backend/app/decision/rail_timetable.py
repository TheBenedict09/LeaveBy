"""Real scheduled trains for a request, from the GB timetable extract. Delays are still simulated elsewhere."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from app.adapters.fallback import haversine_m
from app.core.config import ModelConfig
from app.core.gtfs_extract import day_type
from app.core.timetable import RailTimetable


@dataclass(frozen=True)
class Schedule:
    """Direct trains on the deadline's service day, sorted by departure (unix s). Trains may leave from different
    nearby stations (Glasgow Central and Queen Street are 400 m apart), so each carries its own station names."""

    deps: np.ndarray
    arrs: np.ndarray
    operators: tuple[str, ...]
    headsigns: tuple[str, ...]
    from_names: tuple[str, ...]
    to_names: tuple[str, ...]
    from_coords: tuple[tuple[float, float], ...]  # (lat, lon) of each train's boarding station
    to_coords: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class TrainRun:
    """One real scheduled train, as simulated."""

    depart_ts: int
    arrive_ts: int
    operator: str
    headsign: str
    from_name: str
    to_name: str
    from_coord: tuple[float, float]  # (lat, lon)
    to_coord: tuple[float, float]


class OutOfRange(Exception):
    """The deadline's date is outside the timetable's validity window."""


def stations_near(tt: RailTimetable, lat: float, lon: float, radius_m: float) -> list[str]:
    return [crs for crs, st in tt.stations.items() if haversine_m(lat, lon, st.lat, st.lon) <= radius_m]


def lookup(
    tt: RailTimetable, origin: tuple[float, float], dest: tuple[float, float], deadline_ts: int, cfg: ModelConfig
) -> Schedule | None:
    """Every direct train between any station near the origin and any station near the destination. None when no
    such pair has direct trains at all. Raises OutOfRange when the date is outside the feed. The schedule may be
    empty on a day without service."""
    r = cfg.rail.station_radius_m
    pairs = [
        (a, b)
        for a in stations_near(tt, *origin, r)
        for b in stations_near(tt, *dest, r)
        if a != b and f"{a}-{b}" in tt.pairs
    ]
    if not pairs:
        return None
    tz = ZoneInfo(cfg.rail.timezone)
    day = datetime.fromtimestamp(deadline_ts, UTC).astimezone(tz).date()
    if not tt.valid_from <= day <= tt.valid_to:
        raise OutOfRange
    midnight = datetime.combine(day, time(0), tz)

    def at(m: int) -> int:
        return int((midnight + timedelta(minutes=m)).timestamp())

    # Same-day trains only (no overnight journeys); GTFS minutes past 1440 belong to the next calendar day.
    rows = sorted(
        (
            at(dep),
            at(arr),
            op,
            head,
            tt.stations[a].name,
            tt.stations[b].name,
            (tt.stations[a].lat, tt.stations[a].lon),
            (tt.stations[b].lat, tt.stations[b].lon),
        )
        for a, b in pairs
        for dep, arr, op, head in tt.pairs[f"{a}-{b}"].get(day_type(day), [])
        if dep < 24 * 60
    )
    cols = list(zip(*rows, strict=True)) or [()] * 8
    return Schedule(
        np.array(cols[0], dtype=np.int64),
        np.array(cols[1], dtype=np.int64),
        *(tuple(c) for c in cols[2:]),
    )


def scheduled_departures(s: Schedule, deadline_ts: int, cfg: ModelConfig) -> tuple[np.ndarray, bool]:
    """Indices into the schedule worth simulating, and whether the deadline needs a train before the first one.
    Mirrors the generated timetable: from 'certainly on time' to the first train that is hopelessly late."""
    if not s.deps.size:
        return np.array([], dtype=np.int64), False
    r = cfg.rail
    total = r.access_min * 60 + float(np.median(s.arrs - s.deps)) + r.egress_min * 60
    earliest = deadline_ts - total * cfg.grid.earliest_mult - cfg.grid.pad_min * 60
    first = int(np.searchsorted(s.deps, earliest))
    on_time = np.flatnonzero(s.arrs <= deadline_ts)  # not monotone: a later fast train can beat an earlier slow one
    if on_time.size:
        first = min(first, int(on_time[-1]))  # always keep the last train that can still make it
        last = min(int(on_time[-1]) + 1, len(s.deps) - 1)  # plus one late train so the cliff shows
    else:
        first = last = min(first, len(s.deps) - 1)
    cut_early = first == 0 and s.deps[0] > earliest
    return np.arange(first, last + 1), bool(cut_early)
