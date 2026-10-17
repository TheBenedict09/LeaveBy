"""Cut a small rail timetable out of a national GTFS feed (used by scripts/build_rail_timetable.py).

Keeps only DIRECT trips between a chosen set of stations, for one reference date per day type, so the result
is a few hundred KB instead of the 30 MB feed. Times are minutes after the service day's local midnight and may
exceed 1440 (GTFS allows 24:00:00 and later for trips that run past midnight)."""

import csv
import io
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

DAY_TYPES = ("weekday", "friday", "saturday", "sunday")  # weekday = Monday to Thursday
_WEEKDAY_COL = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def day_type(d: date) -> str:
    return ("weekday", "weekday", "weekday", "weekday", "friday", "saturday", "sunday")[d.weekday()]


def minutes(hms: str) -> int:
    """'25:07:00' -> 1507. GTFS times past midnight stay above 1440."""
    h, m, _ = hms.strip().split(":")
    return int(h) * 60 + int(m)


def _rows(z: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))


def _ymd(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def reference_dates(start: date, end: date) -> dict[str, date]:
    """One typical date per day type, a week into the feed so short-notice changes have settled."""
    out: dict[str, date] = {}
    d = min(start + timedelta(days=7), end)
    while len(out) < len(DAY_TYPES) and d <= end:
        out.setdefault(day_type(d), d)
        d += timedelta(days=1)
    return out


def active_services(z: zipfile.ZipFile, on: date) -> set[str]:
    """service_ids running on a date: calendar.txt weekly pattern, then calendar_dates.txt exceptions."""
    names = set(z.namelist())
    active: set[str] = set()
    if "calendar.txt" in names:
        for r in _rows(z, "calendar.txt"):
            if _ymd(r["start_date"]) <= on <= _ymd(r["end_date"]) and r[_WEEKDAY_COL[on.weekday()]] == "1":
                active.add(r["service_id"])
    if "calendar_dates.txt" in names:
        key = on.strftime("%Y%m%d")
        for r in _rows(z, "calendar_dates.txt"):
            if r["date"] == key:
                (active.add if r["exception_type"] == "1" else active.discard)(r["service_id"])
    return active


def feed_window(z: zipfile.ZipFile) -> tuple[date, date]:
    """feed_info.txt when it gives one (calendar rows can span years), else the span of the calendars."""
    if "feed_info.txt" in z.namelist():
        info = next(_rows(z, "feed_info.txt"), {})
        if info.get("feed_start_date") and info.get("feed_end_date"):
            return _ymd(info["feed_start_date"]), _ymd(info["feed_end_date"])
    starts, ends = [], []
    if "calendar.txt" in z.namelist():
        for r in _rows(z, "calendar.txt"):
            starts.append(_ymd(r["start_date"]))
            ends.append(_ymd(r["end_date"]))
    if "calendar_dates.txt" in z.namelist():
        for r in _rows(z, "calendar_dates.txt"):
            starts.append(_ymd(r["date"]))
            ends.append(_ymd(r["date"]))
    return min(starts), max(ends)


def extract(z: zipfile.ZipFile, wanted: dict[str, str]) -> dict[str, Any]:
    """wanted maps a station code (CRS) to the GTFS stop_id, stop_code or exact stop_name to look for.
    Returns stations, the feed window, the reference dates and, per 'FROM-TO' pair and day type, sorted
    [dep, arr, operator, headsign] rows."""
    stops = list(_rows(z, "stops.txt"))
    code_of: dict[str, str] = {}
    stations: dict[str, dict[str, Any]] = {}
    for crs, key in wanted.items():
        hits = [s for s in stops if key in (s.get("stop_id"), s.get("stop_code"), s.get("stop_name"))]
        if not hits:
            continue
        main = next((s for s in hits if not s.get("parent_station")), hits[0])
        stations[crs] = {"name": main["stop_name"], "lat": float(main["stop_lat"]), "lon": float(main["stop_lon"])}
        for s in stops:  # the station itself and any platforms under it
            if s["stop_id"] in {h["stop_id"] for h in hits} or s.get("parent_station") in {h["stop_id"] for h in hits}:
                code_of[s["stop_id"]] = crs

    start, end = feed_window(z)
    refs = reference_dates(start, end)
    services_by_type = {t: active_services(z, d) for t, d in refs.items()}

    operator = {}
    if "agency.txt" in z.namelist():
        operator = {r["agency_id"]: r["agency_name"] for r in _rows(z, "agency.txt")}
    route_op = {}
    for r in _rows(z, "routes.txt"):
        agency = r.get("agency_id", "")
        route_op[r["route_id"]] = operator.get(agency, agency)
    trips: dict[str, tuple[str, str, set[str]]] = {}
    for r in _rows(z, "trips.txt"):
        types = {t for t, sv in services_by_type.items() if r["service_id"] in sv}
        if types:
            trips[r["trip_id"]] = (route_op.get(r["route_id"], ""), r.get("trip_headsign", ""), types)

    calls: dict[str, list[tuple[int, str, int, int, bool, bool]]] = defaultdict(list)
    for r in _rows(z, "stop_times.txt"):
        crs = code_of.get(r["stop_id"])
        if crs and r["trip_id"] in trips:
            calls[r["trip_id"]].append(
                (
                    int(r["stop_sequence"]),
                    crs,
                    minutes(r["arrival_time"] or r["departure_time"]),
                    minutes(r["departure_time"] or r["arrival_time"]),
                    r.get("pickup_type", "0") != "1",
                    r.get("drop_off_type", "0") != "1",
                )
            )

    pairs: dict[str, dict[str, set[tuple[int, int, str, str]]]] = defaultdict(lambda: defaultdict(set))
    for trip_id, cs in calls.items():
        op, headsign, types = trips[trip_id]
        cs.sort()
        for i, (_, a, _, dep, board, _) in enumerate(cs):
            for _, b, arr, _, _, alight in cs[i + 1 :]:
                if a != b and board and alight:
                    for t in types:
                        pairs[f"{a}-{b}"][t].add((dep, arr, op, headsign))

    return {
        "stations": stations,
        "valid_from": start.isoformat(),
        "valid_to": end.isoformat(),
        "reference_dates": {t: d.isoformat() for t, d in refs.items()},
        "pairs": {p: {t: sorted(map(list, rows)) for t, rows in by_t.items()} for p, by_t in sorted(pairs.items())},
    }
