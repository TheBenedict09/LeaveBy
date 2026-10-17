import json
import zipfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from app.core.config import load_model_config
from app.core.gtfs_extract import day_type, extract, minutes, reference_dates
from app.core.mockdata import load_mock_data
from app.core.timetable import RailTimetable, load_timetable
from app.decision.engine import Problem, RouteInfo, decide, simulate_all
from app.decision.rail_mock import make_rail_noise, simulate_scheduled
from app.decision.rail_timetable import OutOfRange, lookup, scheduled_departures
from tests.helpers import weather

LONDON = ZoneInfo("Europe/London")
GLC, EDB, FAR = (55.8587, -4.2575), (55.9521, -3.1895), (57.0, -5.0)

# A tiny feed: Glasgow (two platforms under a parent) to Edinburgh via Falkirk, weekdays and Sundays.
FEED = {
    "agency.txt": "agency_id,agency_name\nSR,ScotRail\n",
    "feed_info.txt": "feed_publisher_name,feed_start_date,feed_end_date\nTest,20261019,20270117\n",
    "stops.txt": "stop_id,stop_code,stop_name,stop_lat,stop_lon,parent_station\n"
    "GLC,GLC,Glasgow Central,55.8587,-4.2575,\n"
    "GLC1,,Glasgow Central P1,55.8587,-4.2575,GLC\n"
    "FKK,FKK,Falkirk High,55.9920,-3.7920,\n"
    "EDB,EDB,Edinburgh Waverley,55.9521,-3.1895,\n",
    "routes.txt": "route_id,agency_id\nR1,SR\n",
    "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
    "WK,1,1,1,1,1,0,0,20210104,20991231\nSU,0,0,0,0,0,0,1,20210103,20991231\n",  # spans years, like the real feed
    "calendar_dates.txt": "service_id,date,exception_type\nWK,20261103,2\n",  # Tuesday 3 Nov: no WK
    "trips.txt": "route_id,service_id,trip_id,trip_headsign\n"
    "R1,WK,T1,Edinburgh\nR1,WK,T2,Edinburgh\nR1,SU,T3,Edinburgh\nR1,WK,T4,Glasgow Central\n",
    "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"
    "T1,07:45:00,07:45:00,GLC1,1,0,1\nT1,08:05:00,08:06:00,FKK,2,0,0\nT1,08:37:00,08:37:00,EDB,3,1,0\n"
    "T2,23:50:00,23:50:00,GLC1,1,0,1\nT2,24:40:00,24:40:00,EDB,2,1,0\n"
    "T3,09:15:00,09:15:00,GLC,1,0,1\nT3,10:05:00,10:05:00,EDB,2,1,0\n"
    "T4,08:00:00,08:00:00,EDB,1,0,1\nT4,08:50:00,08:50:00,GLC,2,1,0\n",
}


@pytest.fixture
def feed(tmp_path):
    path = tmp_path / "gtfs.zip"
    with zipfile.ZipFile(path, "w") as z:
        for name, text in FEED.items():
            z.writestr(name, text)
    with zipfile.ZipFile(path) as z:
        yield z


@pytest.fixture
def out(feed):
    return extract(feed, {"GLC": "GLC", "EDB": "Edinburgh Waverley", "FKK": "FKK"})


def test_minutes_keep_times_past_midnight():
    assert minutes("07:45:00") == 465 and minutes("24:40:00") == 1480 and minutes("25:07:00") == 1507


def test_day_types_and_reference_dates():
    assert [day_type(date(2026, 10, d)) for d in (19, 22, 23, 24, 25)] == [
        "weekday",
        "weekday",
        "friday",
        "saturday",
        "sunday",
    ]
    refs = reference_dates(date(2026, 10, 19), date(2027, 1, 17))
    assert set(refs) == {"weekday", "friday", "saturday", "sunday"}
    assert all(day_type(d) == t for t, d in refs.items())


def test_extract_finds_direct_trips_per_day_type(out):
    assert set(out["stations"]) == {"GLC", "EDB", "FKK"}
    assert (out["valid_from"], out["valid_to"]) == ("2026-10-19", "2027-01-17")  # from feed_info, not calendar
    assert out["stations"]["EDB"]["name"] == "Edinburgh Waverley"
    wk = out["pairs"]["GLC-EDB"]["weekday"]
    assert [465, 517, "ScotRail", "Edinburgh"] in wk  # platform stop maps to its station
    assert [1430, 1480, "ScotRail", "Edinburgh"] in wk  # arrival past midnight kept as 24:40
    assert out["pairs"]["GLC-EDB"]["sunday"] == [[555, 605, "ScotRail", "Edinburgh"]]
    assert "saturday" not in out["pairs"]["GLC-EDB"]
    assert out["pairs"]["GLC-FKK"]["weekday"] == [[465, 485, "ScotRail", "Edinburgh"]]
    assert out["pairs"]["FKK-EDB"]["weekday"] == [[486, 517, "ScotRail", "Edinburgh"]]
    assert "EDB-GLC" in out["pairs"] and "EDB-FKK" not in out["pairs"]  # only real travel directions


def test_extract_respects_pickup_and_drop_off_rules(out):
    # T1 forbids alighting at Glasgow and boarding at Edinburgh, so nothing runs Edinburgh to Glasgow on T1
    assert all(row[2] == "ScotRail" and row[0] == 480 for row in out["pairs"]["EDB-GLC"]["weekday"])


def timetable(out) -> RailTimetable:
    return RailTimetable.model_validate({**out, "source": "test", "release": "test"})


def at(y, mo, d, h, mi=0) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=LONDON).timestamp())


def test_lookup_uses_the_arrival_date_day_type_and_local_time(out):
    cfg = load_model_config()
    s = lookup(timetable(out), GLC, EDB, at(2026, 11, 2, 9), cfg)  # Monday
    assert s is not None and (s.from_names[0], s.to_names[0]) == ("Glasgow Central", "Edinburgh Waverley")
    assert s.deps[0] == at(2026, 11, 2, 7, 45) and s.arrs[0] == at(2026, 11, 2, 8, 37)
    sunday = lookup(timetable(out), GLC, EDB, at(2026, 11, 8, 11), cfg)
    assert list(sunday.deps) == [at(2026, 11, 8, 9, 15)]
    saturday = lookup(timetable(out), GLC, EDB, at(2026, 11, 7, 11), cfg)
    assert saturday is not None and saturday.deps.size == 0  # covered pair, no service that day


def test_lookup_falls_back_when_far_from_a_station_or_outside_the_feed(out):
    cfg = load_model_config()
    assert lookup(timetable(out), FAR, EDB, at(2026, 11, 2, 9), cfg) is None
    with pytest.raises(OutOfRange):
        lookup(timetable(out), GLC, EDB, at(2027, 3, 1, 9), cfg)


def test_scheduled_departures_keep_one_late_train_and_flag_a_too_early_deadline(out):
    cfg = load_model_config()
    s = lookup(timetable(out), GLC, EDB, at(2026, 11, 2, 9), cfg)
    idx, cut = scheduled_departures(s, at(2026, 11, 2, 9), cfg)
    assert list(idx) == [0, 1] and cut  # 07:45 is on time; 23:50 is the 'late' one; 07:45 is also the first train
    idx, cut = scheduled_departures(s, at(2026, 11, 2, 8, 30), cfg)
    assert list(idx) == [0] and cut and s.arrs[0] > at(2026, 11, 2, 8, 30)


ROUTES = {
    "walk": RouteInfo(75_000.0, 54_000.0, 80.0),
    "bike": RouteInfo(76_000.0, 16_000.0, 80.0),
    "drive": RouteInfo(75_000.0, 4_000.0, 80.0),
}


def run(out, deadline, schedule=True, seed=7):
    cfg = load_model_config()
    w = weather()  # calm everywhere; the engine clamps to the nearest forecast hour
    s = lookup(timetable(out), GLC, EDB, deadline, cfg) if schedule else None
    sim = simulate_all(ROUTES, w, deadline, seed, cfg, load_mock_data(), s)
    p = Problem(deadline_ts=deadline, confidence=0.9, weights={"time": 1.0}, has_car=True, max_walk_m=200_000)
    return sim, decide(sim, p)


def test_engine_rides_the_real_trains_when_covered(out):
    deadline = at(2026, 11, 2, 9)
    sim, d = run(out, deadline)
    access = load_model_config().rail.access_min * 60
    assert list(sim.sims["train"].departures + access) == [at(2026, 11, 2, 7, 45), at(2026, 11, 2, 23, 50)]
    first = sim.train_services[0]
    assert (first.depart_ts, first.arrive_ts, first.operator, first.headsign) == (
        at(2026, 11, 2, 7, 45),
        at(2026, 11, 2, 8, 37),
        "ScotRail",
        "Edinburgh",
    )
    assert (first.from_name, first.to_name, first.from_coord) == ("Glasgow Central", "Edinburgh Waverley", GLC)


def test_engine_falls_back_to_the_generated_timetable_when_not_covered(out):
    sim, _ = run(out, at(2026, 11, 2, 9), schedule=False)
    assert sim.train_services is None and len(sim.sims["train"].departures) > 2


def test_a_deadline_before_the_first_real_train_gets_the_plain_reason(out):
    _, d = run(out, at(2026, 11, 2, 8, 30))
    train = next(o for o in d.options if o.mode == "train")
    assert not train.feasible and train.infeasible_reason == "No train runs early enough"


def test_a_day_without_direct_trains_says_so(out):
    _, d = run(out, at(2026, 11, 7, 11))  # Saturday
    train = next(o for o in d.options if o.mode == "train")
    assert not train.feasible and train.infeasible_reason == "No direct train runs that day"


def test_same_request_same_result_on_the_real_timetable(out):
    a, _ = run(out, at(2026, 11, 2, 9), seed=3)
    b, _ = run(out, at(2026, 11, 2, 9), seed=3)
    assert np.array_equal(a.sims["train"].durations, b.sims["train"].durations)


def test_calm_weather_punctuality_matches_the_published_figure():
    cfg = load_model_config()
    w = weather(members=51, gust=0.0)
    deps = np.array([int(w.times[3])], dtype=np.int64)
    ride = 50 * 60.0
    sim = simulate_scheduled(np.array([ride]), w, deps, make_rail_noise(11, 51, 400), cfg)
    late_by = sim.durations - (cfg.rail.access_min + cfg.rail.egress_min) * 60 - ride
    assert abs((late_by <= 5 * 60).mean() - cfg.rail.calm_within_5min_target) <= 0.02


def test_the_committed_extract_loads_if_present():
    tt = load_timetable()
    if tt is None:
        pytest.skip("data/rail_timetable.json not built yet (make rail-data)")
    assert "Rail Delivery Group" in tt.source and tt.valid_from < tt.valid_to
    assert all(set(by_type) <= {"weekday", "friday", "saturday", "sunday"} for by_type in tt.pairs.values())
    json.dumps(tt.model_dump(mode="json"))  # round-trips


def test_trains_from_every_station_near_the_origin_are_merged_and_named(out):
    tt = timetable(out).model_copy(deep=True)
    # A second Glasgow station 400 m away with a faster train, like Queen Street
    tt.stations["GLQ"] = tt.stations["GLC"].model_copy(update={"name": "Glasgow Queen Street", "lat": 55.8622})
    tt.pairs["GLQ-EDB"] = {"weekday": [(480, 530, "ScotRail", "Edinburgh")]}
    s = lookup(tt, GLC, EDB, at(2026, 11, 2, 9), load_model_config())
    assert [n for n in s.from_names[:2]] == ["Glasgow Central", "Glasgow Queen Street"]
    assert list(s.deps[:2]) == [at(2026, 11, 2, 7, 45), at(2026, 11, 2, 8, 0)]


def test_a_later_faster_train_is_never_cut_off_by_an_earlier_slow_one(out):
    tt = timetable(out).model_copy(deep=True)
    tt.pairs["GLC-EDB"]["weekday"] = [(400, 560, "Slow", "X"), (470, 520, "Fast", "Y")]  # 06:40-09:20, 07:50-08:40
    s = lookup(tt, GLC, EDB, at(2026, 11, 2, 9), load_model_config())
    idx, _ = scheduled_departures(s, at(2026, 11, 2, 9), load_model_config())
    assert 1 in idx  # the fast 07:50 that arrives in time is simulated
