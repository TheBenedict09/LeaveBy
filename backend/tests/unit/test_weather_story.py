import numpy as np

from app.core.config import load_model_config
from app.core.mockdata import load_mock_data
from app.decision.engine import decide, simulate_all
from app.decision.weather_story import dry_weather, extra_minutes, members_at, point, stormy, tips, train_late_risk
from tests.helpers import DEADLINE, weather
from tests.unit.test_decide import ROUTES, problem

CFG = load_model_config()


def run(w):
    sim = simulate_all(ROUTES, w, DEADLINE, 11, CFG, load_mock_data())
    dry = simulate_all(ROUTES, dry_weather(w), DEADLINE, 11, CFG, load_mock_data())
    return decide(sim, problem()), decide(dry, problem())


def test_dry_weather_keeps_the_shape_and_removes_rain_wind_and_fog():
    w = weather(precip=3.0, wind=9.0, gust=20.0, vis=300.0)
    d = dry_weather(w)
    assert d.precip_mm_h.shape == w.precip_mm_h.shape and d.n_members == w.n_members
    assert not d.precip_mm_h.any() and not d.gust_ms.any() and (d.visibility_m > 2000).all()


def test_rain_costs_minutes_and_a_calm_morning_costs_none():
    wet, dry = run(weather(precip=4.0))
    extra = extra_minutes(wet, dry)
    assert extra["bike"] > extra["drive"] > 0  # the model slows bikes more than cars in rain
    calm, calm_dry = run(weather())
    assert all(v == 0 for v in extra_minutes(calm, calm_dry).values())


def test_point_counts_forecasts_with_rain_in_plain_numbers():
    w = weather(precip=2.0, gust=15.0, members=6)
    p = point(w, DEADLINE)
    assert (p.members, p.members_with_rain) == (6, 6)
    assert p.rain_mm_h_median == 2.0 and round(p.gust_mph_median) == 34
    assert len(members_at(w, DEADLINE)) == 6


def test_gusts_raise_the_train_late_risk_from_the_calibrated_calm_value():
    calm, now = train_late_risk(weather(gust=25.0), DEADLINE, CFG)
    assert abs(calm - (1 - CFG.rail.calm_within_5min_target)) < 0.005  # matches the published calibration
    assert now > calm


def test_tips_only_say_what_the_data_supports():
    wet = weather(precip=3.0, gust=20.0, temp=0.0)
    d, dry = run(wet)
    lines = tips(wet, point(wet, DEADLINE - 3600), DEADLINE - 3600, DEADLINE, extra_minutes(d, dry), d, CFG)
    assert any("waterproof" in t for t in lines) and any("Gusts" in t for t in lines) and any("ice" in t for t in lines)
    calm = weather()
    d, dry = run(calm)
    assert tips(calm, point(calm, DEADLINE - 3600), DEADLINE - 3600, DEADLINE, extra_minutes(d, dry), d, CFG) == []
    assert np.isfinite(point(calm, DEADLINE).rain_mm_h_p90)


def test_the_demo_storm_adds_the_configured_amounts_and_is_deterministic():
    w = weather(precip=0.5, gust=4.0, vis=24000.0)
    s = stormy(w, CFG)
    assert np.allclose(s.precip_mm_h, 0.5 + CFG.storm_demo.rain_add_mm_h)
    assert np.allclose(s.gust_ms, 4.0 + CFG.storm_demo.gust_add_ms)
    assert (s.visibility_m <= CFG.storm_demo.visibility_cap_m).all()
    assert np.array_equal(stormy(w, CFG).precip_mm_h, s.precip_mm_h)
