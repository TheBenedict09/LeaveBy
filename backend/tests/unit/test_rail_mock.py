import numpy as np
import pytest

from app.core.config import load_model_config
from app.decision.rail_mock import make_rail_noise, rail_times, simulate_train, train_departures
from app.decision.summarise import p_on_time
from tests.helpers import DEADLINE, weather

DIST = 12_000.0
K = 20


def run(w=None, cfg=None, seed=3):
    cfg = cfg or load_model_config()
    w = w or weather()
    deps = train_departures(DEADLINE, DIST, cfg)
    return simulate_train(DIST, w, deps, make_rail_noise(seed, w.n_members, K), cfg)


def test_trains_run_on_the_headway_and_bracket_the_transition():
    cfg = load_model_config()
    deps = train_departures(DEADLINE, DIST, cfg)
    step = cfg.rail.headway_min * 60
    assert (deps % step == 0).all()
    assert (np.diff(deps) == step).all()
    access_s, ride_s, egress_s = rail_times(DIST, cfg)
    assert deps[0] < DEADLINE - (access_s + ride_s + egress_s) < deps[-1] + step


def test_result_is_keyed_by_when_you_leave_home():
    cfg = load_model_config()
    deps = train_departures(DEADLINE, DIST, cfg)
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
        simulate_train(DIST, w, train_departures(DEADLINE, DIST, cfg), make_rail_noise(1, 5, K), cfg)
