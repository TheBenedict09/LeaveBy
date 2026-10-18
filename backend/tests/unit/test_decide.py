import numpy as np

from app.core.config import load_model_config
from app.core.mockdata import load_mock_data
from app.decision.engine import MODES, Problem, RouteInfo, decide, simulate_all
from app.decision.explain import explain
from app.decision.simulate import SimResult
from tests.helpers import DEADLINE, NIGHT_DEADLINE, weather

WEIGHTS = {"time": 0.4, "cost": 0.2, "carbon": 0.2, "accessibility": 0.2}
# A 12 km city-to-suburb trip: every mode is a real contender.
ROUTES = {
    "walk": RouteInfo(12_500.0, 9_000.0, 270.0),
    "bike": RouteInfo(12_800.0, 2_700.0, 270.0),
    "drive": RouteInfo(13_000.0, 1_500.0, 270.0),
}


def sim(w=None, seed=11, data=None):
    return simulate_all(ROUTES, w or weather(precip=1.0), DEADLINE, seed, load_model_config(), data or load_mock_data())


def problem(**kw):
    base = dict(deadline_ts=DEADLINE, confidence=0.95, weights=WEIGHTS, has_car=True, max_walk_m=20_000)
    return Problem(**(base | kw))


def test_all_four_modes_are_simulated_with_shared_member_count():
    s = sim()
    assert set(s.sims) == set(MODES) == set(s.facts)
    assert s.n_members == 6
    assert all(r.durations.shape[1] == 6 for r in s.sims.values())


def test_options_are_ranked_contiguously_and_infeasible_ones_stay_visible():
    d = decide(sim(), problem(has_car=False))
    ranked = [o for o in d.options if o.rank is not None]
    assert [o.rank for o in ranked] == list(range(1, len(ranked) + 1))
    assert d.winner is d.options[0] and d.winner.rank == 1
    assert len(d.options) == 4
    drive = next(o for o in d.options if o.mode == "drive")
    assert not drive.feasible and drive.infeasible_reason == "No car available" and drive.rank is None


def test_walking_limit_is_a_hard_constraint():
    d = decide(sim(), problem(max_walk_m=1200))
    walk = next(o for o in d.options if o.mode == "walk")
    assert not walk.feasible and "walking limit" in walk.infeasible_reason


def test_cycling_limit_is_a_hard_constraint():
    d = decide(sim(), problem(max_bike_m=5_000))
    bike = next(o for o in d.options if o.mode == "bike")
    assert not bike.feasible and bike.infeasible_reason == "Further than your cycling limit"


def test_step_free_requirement_excludes_non_step_free_modes():
    data = load_mock_data().model_copy(deep=True)
    data.accessibility["train"].step_free = False
    d = decide(sim(data=data), problem(step_free=True))
    train = next(o for o in d.options if o.mode == "train")
    assert not train.feasible and train.infeasible_reason == "No step-free route"


def test_a_mode_that_cannot_make_it_says_why():
    s = sim()
    bike = s.sims["bike"]
    s.sims["bike"] = SimResult("bike", bike.departures, np.full_like(bike.durations, 1e7))
    d = decide(s, problem())
    opt = next(o for o in d.options if o.mode == "bike")
    assert not opt.feasible and opt.rank is None and opt.summary.leave_by_ts is None
    assert opt.infeasible_reason == "Cannot reach with 95% confidence by the deadline"


def test_higher_confidence_never_means_leaving_later():
    s = sim()
    lo, hi = decide(s, problem(confidence=0.8)), decide(s, problem(confidence=0.99))
    for a in lo.options:
        b = next(o for o in hi.options if o.mode == a.mode)
        if a.summary.leave_by_ts is not None and b.summary.leave_by_ts is not None:
            assert b.summary.leave_by_ts <= a.summary.leave_by_ts


def test_same_inputs_give_identical_decisions():
    a, b = decide(sim(seed=4), problem()), decide(sim(seed=4), problem())
    assert [(o.mode, o.rank, o.score) for o in a.options] == [(o.mode, o.rank, o.score) for o in b.options]


def test_changing_priorities_re_ranks_without_resimulating():
    s = sim()
    time_first = decide(s, problem(weights={"time": 1, "cost": 0, "carbon": 0, "accessibility": 0}))
    carbon_first = decide(s, problem(weights={"time": 0, "cost": 0, "carbon": 1, "accessibility": 0}))
    assert time_first.winner.mode != carbon_first.winner.mode


def test_hedge_is_a_different_feasible_mode_and_obeys_the_joint_probability_bound():
    d = decide(sim(w=weather(precip=2.0, gust=22.0)), problem())
    assert d.hedge is not None
    assert d.hedge.backup_mode != d.winner.mode
    assert next(o for o in d.options if o.mode == d.hedge.backup_mode).feasible
    assert d.hedge.p_both_late <= min(d.hedge.p_late_main, d.hedge.p_late_backup) + 1e-12
    assert decide(sim(), problem(hedge=False)).hedge is None


def test_every_flip_point_names_a_non_winner():
    d = decide(sim(), problem())
    assert all(f.mode != d.winner.mode for f in d.flips)


def test_explanation_is_built_only_from_decision_numbers():
    d = decide(sim(), problem())
    e = explain(d)
    assert e.because and "95%" in e.because[0]
    assert len(e.tradeoffs) == sum(1 for o in d.options if o.feasible) - 1
    text = " ".join(e.because + e.tradeoffs + e.flip_points + ([e.hedge] if e.hedge else []))
    assert "nan" not in text.lower()


def test_when_nothing_is_feasible_there_is_no_winner_and_a_plain_message():
    data = load_mock_data().model_copy(deep=True)
    for a in data.accessibility.values():
        a.step_free = False
    d = decide(sim(data=data), problem(step_free=True))
    assert d.winner is None and d.hedge is None and d.flips == []
    assert all(o.infeasible_reason == "No step-free route" for o in d.options)
    assert "No option reaches 95%" in explain(d).because[0]


def test_luggage_lowers_the_accessibility_of_walking_and_cycling_more_than_driving():
    s = sim()
    w = {"time": 0, "cost": 0, "carbon": 0, "accessibility": 1}
    assert decide(s, problem(weights=w, has_luggage=True)).winner.mode in {"drive", "train"}
    assert np.isfinite(decide(s, problem(weights=w, has_luggage=True)).winner.score)


def test_probability_at_leave_by_meets_confidence_for_every_feasible_mode():
    d = decide(sim(), problem(confidence=0.9))
    for o in d.options:
        if o.summary.feasible:
            assert o.summary.p_on_time >= 0.9


def test_a_deadline_before_the_first_train_makes_rail_infeasible_with_a_plain_reason():
    # 00:46 UK time: no train runs then, and the first one of the day is too late.
    night = simulate_all(ROUTES, weather(precip=1.0), NIGHT_DEADLINE, 11, load_model_config(), load_mock_data())
    train = next(o for o in decide(night, problem(deadline_ts=NIGHT_DEADLINE)).options if o.mode == "train")
    assert not train.feasible and train.infeasible_reason == "No train runs early enough"


def test_a_trip_later_today_never_leaves_in_the_past():
    now = DEADLINE - 2 * 3600  # planning two hours ahead: part of every grid is already behind us
    s = simulate_all(ROUTES, weather(precip=1.0), DEADLINE, 11, load_model_config(), load_mock_data(), not_before=now)
    for m in MODES:
        assert s.sims[m].departures.min() >= now
    full = sim()
    cut = [m for m in ("walk", "bike", "drive") if full.sims[m].departures[0] < now]
    assert cut  # the case is meaningful: some grid really did start in the past
    for m in cut:
        assert s.sims[m].departures[0] == now  # leaving right now replaces the departures cut
    for o in decide(s, problem()).options:
        assert o.summary.leave_by_ts is None or o.summary.leave_by_ts >= now


def test_when_every_useful_train_has_left_the_train_says_so():
    late = DEADLINE - 60  # one minute before the deadline
    s = simulate_all(ROUTES, weather(precip=1.0), DEADLINE, 11, load_model_config(), load_mock_data(), not_before=late)
    d = decide(s, problem())
    train = next(o for o in d.options if o.mode == "train")
    assert train.infeasible_reason == "Every train that gets you there in time has already left"
    assert d.winner is None
