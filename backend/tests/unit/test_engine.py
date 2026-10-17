import json
from pathlib import Path

import numpy as np
import pytest

from app.adapters.weather import WeatherEnsemble, parse_ensemble
from app.core.config import load_model_config
from app.core.seed import seed_from
from app.decision.simulate import SimResult, departure_grid, make_noise, simulate
from app.decision.summarise import leave_by_index, p_on_time, summarise
from app.decision.weather_factor import conditions_at, headwind_ms, speed_factor

ROOT = Path(__file__).resolve().parents[3]
T0 = 1_792_000_000
M, K, H = 6, 20, 120
DEADLINE = T0 + 30 * 3600


def weather(precip=0.0, wind=0.0, wind_dir=0.0, gust=0.0, temp=10.0, vis=24000.0, members=M) -> WeatherEnsemble:
    def full(v):
        return np.full((members, H), float(v))

    return WeatherEnsemble(
        lat=55.86,
        lon=-4.26,
        times=T0 + 3600 * np.arange(H, dtype=np.int64),
        precip_mm_h=full(precip),
        wind_ms=full(wind),
        wind_dir_deg=full(wind_dir),
        gust_ms=full(gust),
        temp_c=full(temp),
        visibility_m=full(vis),
    )


def run(mode="drive", base=4000.0, bearing=90.0, w=None, cfg=None, seed=1):
    cfg = cfg or load_model_config()
    w = w or weather()
    deps = departure_grid(DEADLINE, base, cfg)
    return simulate(mode, base, bearing, w, deps, make_noise(seed, w.n_members, K), cfg)


def test_config_loads_and_noise_ordering_matches_blueprint():
    s = load_model_config().noise.sigma
    assert s["drive"] > s["bike"] > s["walk"] > 0


def test_seed_is_stable_and_order_independent():
    assert seed_from({"a": 1, "b": 2}) == seed_from({"b": 2, "a": 1})
    assert seed_from({"a": 1}) != seed_from({"a": 2})


def test_grid_is_aligned_and_brackets_the_deadline_transition():
    deps = departure_grid(DEADLINE, 4000.0, load_model_config())
    assert (deps % 300 == 0).all()
    assert deps[0] < DEADLINE - 4000 < deps[-1]
    assert (np.diff(deps) == 300).all()


def test_zero_weather_zero_noise_equals_plain_routing_duration():
    cfg = load_model_config().model_copy(deep=True)
    cfg.noise.sigma = {"walk": 0.0, "bike": 0.0, "drive": 0.0}
    for mode in ("walk", "bike", "drive"):
        sim = run(mode=mode, base=1234.0, cfg=cfg)
        assert np.allclose(sim.durations, 1234.0)


def test_p_on_time_never_increases_with_later_departure():
    sim = run(w=weather(precip=2.0, gust=20.0))
    p = p_on_time(sim, DEADLINE)
    assert (np.diff(p) <= 1e-12).all()


def test_cliff_runs_from_certain_to_hopeless():
    p = p_on_time(run(), DEADLINE)
    assert p[0] > 0.99
    assert p[-1] < 0.15


def test_higher_confidence_never_means_leaving_later():
    p = p_on_time(run(w=weather(precip=1.0)), DEADLINE)
    idx = [leave_by_index(p, c) for c in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99)]
    idx = [-1 if i is None else i for i in idx]
    assert idx == sorted(idx, reverse=True)


def test_leave_by_is_the_last_departure_that_meets_confidence():
    sim = run(w=weather(precip=1.0))
    s = summarise(sim, DEADLINE, 0.95)
    p = p_on_time(sim, DEADLINE)
    assert s.feasible and s.leave_by_ts is not None
    assert p[s.ref_index] >= 0.95
    assert (p[s.ref_index + 1 :] < 0.95).all()
    assert s.p_on_time == pytest.approx(p[s.ref_index])


def test_same_seed_same_output_different_seed_different_output():
    a, b, c = run(seed=7), run(seed=7), run(seed=8)
    assert np.array_equal(a.durations, b.durations)
    assert not np.array_equal(a.durations, c.durations)


def test_noise_field_is_shared_across_modes():
    z1, z2 = make_noise(5, M, K), make_noise(5, M, K)
    assert np.array_equal(z1, z2) and z1.shape == (M, K)


def test_rain_slows_bike_and_walk_and_drive():
    for mode in ("walk", "bike", "drive"):
        dry = run(mode=mode, w=weather(precip=0.0)).durations.mean()
        wet = run(mode=mode, w=weather(precip=5.0)).durations.mean()
        assert wet > dry


def test_headwind_slows_bike_but_tailwind_does_not_speed_it_up():
    calm = run(mode="bike", bearing=90, w=weather(wind=0.0)).durations.mean()
    head = run(mode="bike", bearing=90, w=weather(wind=10.0, wind_dir=90.0)).durations.mean()
    tail = run(mode="bike", bearing=90, w=weather(wind=10.0, wind_dir=270.0)).durations.mean()
    assert head > calm
    assert tail == pytest.approx(calm)


def test_headwind_component_geometry():
    w = weather(wind=10.0, wind_dir=90.0)
    c = conditions_at(w, np.array([0]))
    assert headwind_ms(c, 90.0)[0, 0] == pytest.approx(10.0)
    assert headwind_ms(c, 270.0)[0, 0] == pytest.approx(-10.0)
    assert headwind_ms(c, 0.0)[0, 0] == pytest.approx(0.0, abs=1e-9)


def test_speed_factor_stays_in_bounds_under_extreme_weather():
    cfg = load_model_config()
    w = weather(precip=80.0, wind=40.0, wind_dir=90.0, gust=60.0, temp=-10.0, vis=10.0)
    c = conditions_at(w, np.array([0, 1]))
    for mode in ("walk", "bike", "drive"):
        f = speed_factor(mode, c, 90.0, cfg)
        assert (f >= cfg.speed.min_factor).all() and (f <= 1.0).all()


def test_missing_weather_values_do_not_poison_results():
    w = weather()
    w.precip_mm_h[:] = np.nan
    w.wind_dir_deg[:] = np.nan
    w.visibility_m[:] = np.nan
    sim = run(mode="bike", w=w)
    assert np.isfinite(sim.durations).all()


def test_journey_at_risk_is_zero_without_noise_and_positive_with_noise():
    cfg = load_model_config().model_copy(deep=True)
    cfg.noise.sigma = {"walk": 0.0, "bike": 0.0, "drive": 0.0}
    assert summarise(run(cfg=cfg), DEADLINE, 0.95).journey_at_risk_min == pytest.approx(0.0, abs=1e-9)
    assert summarise(run(), DEADLINE, 0.95).journey_at_risk_min > 0


def test_infeasible_mode_is_reported_not_hidden():
    sim = SimResult("bike", np.array([0, 300, 600], dtype=np.int64), np.full((3, 4, 5), 1e6))
    s = summarise(sim, 1000, 0.95)
    assert s.feasible is False and s.leave_by_ts is None
    assert s.p_on_time == 0.0
    assert len(s.cliff) == 3


def test_summary_counts_are_consistent():
    s = summarise(run(w=weather(precip=3.0)), DEADLINE, 0.9)
    assert s.total_scenarios == M * K
    assert len(s.scenario_arrivals) == M
    assert s.on_time_scenarios / s.total_scenarios == pytest.approx(s.p_on_time)
    assert 0 <= s.on_time_scenarios <= s.total_scenarios
    assert s.arrival_p05 <= s.arrival_p50 <= s.arrival_p95


@pytest.mark.skipif(not (ROOT / "fixtures/raw/weather_glasgow.json").exists(), reason="needs real fixture")
def test_engine_runs_on_real_forecast_and_real_route():
    w = parse_ensemble(json.loads((ROOT / "fixtures/raw/weather_glasgow.json").read_text()))
    cfg = load_model_config()
    deadline = int(w.times[0]) + 30 * 3600
    base = 4027.3  # Glasgow Central -> Edinburgh Waverley by car, from the real OSRM response
    deps = departure_grid(deadline, base, cfg)
    sim = simulate("drive", base, 81.0, w, deps, make_noise(seed_from("real"), w.n_members, cfg.noise.n_draws), cfg)
    s = summarise(sim, deadline, 0.95)
    assert s.total_scenarios == 51 * cfg.noise.n_draws
    assert s.feasible and s.leave_by_ts < deadline - base * 0.9
    assert 0.95 <= s.p_on_time <= 1.0
