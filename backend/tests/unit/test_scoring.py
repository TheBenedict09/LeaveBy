import pytest

from app.decision.scoring import (
    CRITERIA,
    apply_flip,
    composite,
    flip_points,
    normalise_criteria,
    normalise_weights,
    rank_modes,
)

RAW = {
    "train": {"time": 90.0, "cost": 14.0, "carbon": 3.0, "accessibility": 0.8},
    "bike": {"time": 60.0, "cost": 0.0, "carbon": 0.0, "accessibility": 0.5},
    "drive": {"time": 80.0, "cost": 9.0, "carbon": 8.0, "accessibility": 0.9},
}
EVEN = {c: 0.25 for c in CRITERIA}
P = {"train": 0.96, "bike": 0.95, "drive": 0.95}
COST = {m: RAW[m]["cost"] for m in RAW}


def winner(weights):
    norm = normalise_criteria(RAW)
    return rank_modes(composite(norm, normalise_weights(weights)), P, COST)[0]


def test_weights_renormalise_to_one():
    w = normalise_weights({"time": 2, "cost": 2, "carbon": 0, "accessibility": 0})
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["time"] == pytest.approx(0.5)


@pytest.mark.parametrize("bad", [{"time": 0, "cost": 0, "carbon": 0, "accessibility": 0}, {"time": -1, "cost": 2}])
def test_bad_weights_rejected(bad):
    with pytest.raises(ValueError):
        normalise_weights(bad)


def test_normalised_scores_stay_in_unit_interval_and_orientation_is_right():
    n = normalise_criteria(RAW)
    for m in n:
        assert all(0.0 <= v <= 1.0 for v in n[m].values())
    assert n["bike"]["time"] == 1.0 and n["train"]["time"] == 0.0  # less time is better
    assert n["drive"]["accessibility"] == 1.0 and n["bike"]["accessibility"] == 0.0  # more access is better


def test_single_option_and_ties_score_one():
    n = normalise_criteria({"train": RAW["train"]})
    assert all(v == 1.0 for v in n["train"].values())
    same = normalise_criteria({"a": RAW["train"], "b": dict(RAW["train"])})
    assert all(v == 1.0 for m in same for v in same[m].values())


def test_composite_is_within_unit_interval():
    s = composite(normalise_criteria(RAW), normalise_weights(EVEN))
    assert all(0.0 <= v <= 1.0 + 1e-12 for v in s.values())


def test_priorities_change_the_winner():
    assert winner({"time": 1, "cost": 0, "carbon": 0, "accessibility": 0}) == "bike"
    assert winner({"time": 0, "cost": 0, "carbon": 0, "accessibility": 1}) == "drive"


def test_tie_break_prefers_higher_p_on_time_then_lower_cost():
    scores = {"a": 0.5, "b": 0.5, "c": 0.5}
    order = rank_modes(scores, {"a": 0.95, "b": 0.97, "c": 0.97}, {"a": 1.0, "b": 5.0, "c": 2.0})
    assert order == ["c", "b", "a"]


def test_every_flip_point_really_changes_the_winner():
    norm = normalise_criteria(RAW)
    w0 = {"time": 0.7, "cost": 0.1, "carbon": 0.1, "accessibility": 0.1}
    base = rank_modes(composite(norm, normalise_weights(w0)), P, COST)[0]
    flips = flip_points(norm, w0, P, COST)
    assert flips, "this setup should have at least one flip point"
    for fp in flips:
        assert fp.mode != base
        assert fp.to_weight > fp.from_weight
        w = apply_flip(w0, fp)
        assert sum(w.values()) == pytest.approx(1.0)
        assert rank_modes(composite(norm, w), P, COST)[0] == fp.mode


def test_option_that_can_never_win_has_no_flip_point():
    raw = {
        "good": {"time": 10.0, "cost": 1.0, "carbon": 1.0, "accessibility": 0.9},
        "worse": {"time": 20.0, "cost": 2.0, "carbon": 2.0, "accessibility": 0.5},
    }
    p, c = {"good": 0.96, "worse": 0.96}, {"good": 1.0, "worse": 2.0}
    assert flip_points(normalise_criteria(raw), EVEN, p, c) == []
