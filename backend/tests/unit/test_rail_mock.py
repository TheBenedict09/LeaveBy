from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from app.core.config import load_model_config
from app.decision.rail_mock import avg_speed_kmh, make_rail_noise, rail_times, simulate_train, train_departures
from app.decision.summarise import p_on_time
from tests.helpers import DEADLINE as NIGHT
from tests.helpers import weather

DEADLINE = NIGHT + 9 * 3600  # helpers' deadline is 00:46 UK time, when no train runs; use 09:46

DIST = 12_000.0
K = 20


def run(w=None, cfg=None, seed=3):
    cfg = cfg or load_model_config()
    w = w or weather()
    deps = train_departures(DEADLINE, DIST, cfg)[0]
    return simulate_train(DIST, w, deps, make_rail_noise(seed, w.n_members, K), cfg)


def test_trains_run_on_the_headway_and_bracket_the_transition():
    cfg = load_model_config()
    deps = train_departures(DEADLINE, DIST, cfg)[0]
    step = cfg.rail.headway_min * 60
    assert (deps % step == 0).all()
    assert (np.diff(deps) == step).all()
    access_s, ride_s, egress_s = rail_times(DIST, cfg)
    assert deps[0] < DEADLINE - (access_s + ride_s + egress_s) < deps[-1] + step


def test_result_is_keyed_by_when_you_leave_home():
    cfg = load_model_config()
    deps = train_departures(DEADLINE, DIST, cfg)[0]
    sim = run()
    access_s, _, _ = rail_times(DIST, cfg)
    assert np.array_equal(sim.departures, deps - int(round(access_s)))


def test_no_delay_chance_means_the_scheduled_duration_exactly():
    cfg = load_model_config().model_copy(deep=True)
    cfg.rail.p_on_time_base = 1.0
    sim = run(cfg=cfg)
    access_s, ride_s, egress_s = rail_times(DIST, cfg)
    assert np.allclose(sim.durations, access_s + ride_s + egress_s)


def test_delays_only_ever_add_time():
    cfg = load_model_config()
    access_s, ride_s, egress_s = rail_times(DIST, cfg)
    sim = run()
    assert (sim.durations >= access_s + ride_s + egress_s - 1e-9).all()
    assert sim.durations.max() <= access_s + ride_s + egress_s + cfg.rail.delay_cap_min * 60 + 1e-9


def test_strong_gusts_make_the_train_slower_on_average():
    calm = run(w=weather(gust=0.0)).durations.mean()
    windy = run(w=weather(gust=35.0)).durations.mean()
    assert windy > calm


def test_p_on_time_never_increases_with_later_departure():
    p = p_on_time(run(w=weather(gust=20.0)), DEADLINE)
    assert (np.diff(p) <= 1e-12).all()


def test_same_seed_same_result():
    assert np.array_equal(run(seed=5).durations, run(seed=5).durations)
    assert not np.array_equal(run(seed=5).durations, run(seed=6).durations)


def test_member_mismatch_is_rejected():
    cfg = load_model_config()
    w = weather(members=6)
    with pytest.raises(ValueError):
        simulate_train(DIST, w, train_departures(DEADLINE, DIST, cfg)[0], make_rail_noise(1, 5, K), cfg)


LONDON = ZoneInfo("Europe/London")


def uk(*args) -> int:
    return int(datetime(*args, tzinfo=LONDON).timestamp())


def local_hm(ts) -> str:
    return datetime.fromtimestamp(int(ts), UTC).astimezone(LONDON).strftime("%H:%M")


@pytest.mark.parametrize("deadline", [uk(2026, 7, 15, 7, 0), uk(2026, 12, 15, 7, 0)])  # BST and GMT
def test_no_train_leaves_outside_the_service_window(deadline):
    cfg = load_model_config()
    deps, cut_early = train_departures(deadline, 75_000.0, cfg)
    assert all("05:30" <= local_hm(t) <= "23:30" for t in deps)
    assert local_hm(deps[0]) == "05:30" and cut_early  # an earlier train would be needed but does not run


def test_daytime_deadline_is_not_cut():
    deps, cut_early = train_departures(uk(2026, 7, 15, 13, 0), 75_000.0, load_model_config())
    assert not cut_early and len(deps) > 1


def test_no_overnight_trains_so_a_long_early_trip_gets_only_the_first_train_of_the_day():
    cfg = load_model_config()
    deadline = uk(2026, 7, 15, 9, 0)  # Glasgow to London by 09:00 would need to leave the evening before
    deps, cut_early = train_departures(deadline, 650_000.0, cfg)
    assert cut_early and local_hm(deps[0]) == "05:30"
    assert all(datetime.fromtimestamp(int(t), UTC).astimezone(LONDON).day == 15 for t in deps)
    access_s, ride_s, egress_s = rail_times(650_000.0, cfg)
    assert deps[0] + ride_s + egress_s > deadline  # even the first train arrives too late


def test_speed_table_rises_with_distance():
    cfg = load_model_config()
    speeds = [avg_speed_kmh(km * 1000.0, cfg) for km in range(5, 900, 5)]
    assert all(b >= a for a, b in zip(speeds, speeds[1:], strict=False))


@pytest.mark.parametrize(
    ("road_km", "lo_min", "hi_min"),
    [(75, 50, 60), (130, 75, 90), (235, 150, 165), (650, 270, 300)],  # Edinburgh, Dundee, Aberdeen, London
)
def test_scheduled_ride_times_are_plausible(road_km, lo_min, hi_min):
    _, ride_s, _ = rail_times(road_km * 1000.0, load_model_config())
    assert lo_min <= ride_s / 60 <= hi_min
