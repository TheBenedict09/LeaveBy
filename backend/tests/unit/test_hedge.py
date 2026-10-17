import numpy as np
import pytest

from app.decision.hedge import choose_hedge


def mask(*late_idx, n=10):
    a = np.zeros((n, 1), dtype=bool)
    a[list(late_idx), 0] = True
    return a


def test_picks_the_backup_that_fails_on_different_mornings():
    late = {
        "main": mask(0, 1),
        "overlapping": mask(0, 1, 2),  # late on exactly the same bad mornings
        "independent": mask(7, 8, 9),  # late on other mornings
    }
    h = choose_hedge("main", late, {"main": 100, "overlapping": 90, "independent": 80})
    assert h is not None
    assert h.backup_mode == "independent"
    assert h.leave_by_ts == 80
    assert h.p_both_late == 0.0 and h.both_late_scenarios == 0
    assert h.total_scenarios == 10


def test_joint_probability_never_exceeds_either_individual_probability():
    rng = np.random.default_rng(0)
    for _ in range(25):
        late = {m: rng.random((8, 5)) < rng.random() for m in ("a", "b", "c")}
        h = choose_hedge("a", late, {"a": 1, "b": 2, "c": 3})
        assert h.p_both_late <= min(h.p_late_main, h.p_late_backup) + 1e-12


def test_no_hedge_without_an_alternative():
    assert choose_hedge("main", {"main": mask(1)}, {"main": 1}) is None
    assert choose_hedge("missing", {"a": mask(1), "b": mask(2)}, {"a": 1, "b": 2}) is None


def test_ties_break_on_lower_own_lateness():
    late = {"main": mask(0), "x": mask(5, 6), "y": mask(5)}
    h = choose_hedge("main", late, {"main": 1, "x": 2, "y": 3})
    assert h.backup_mode == "y"
    assert h.p_late_backup == pytest.approx(0.1)
