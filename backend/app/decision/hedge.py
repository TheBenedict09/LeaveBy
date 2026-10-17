"""Backup plan (blueprint 5.8): the alternative least likely to be late on the SAME mornings as the main plan.
Scenarios are paired by (ensemble member, noise draw), which is why the noise is shared across modes."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Hedge:
    backup_mode: str
    leave_by_ts: int
    p_both_late: float
    p_late_main: float
    p_late_backup: float
    both_late_scenarios: int
    total_scenarios: int


def choose_hedge(main: str, late: dict[str, np.ndarray], leave_by_ts: dict[str, int]) -> Hedge | None:
    """late[mode] is a boolean (M, K) array: was this scenario late if you follow that plan? Only feasible modes."""
    candidates = [m for m in late if m != main]
    if main not in late or not candidates:
        return None
    lm = late[main]

    def joint(m: str) -> float:
        return float((lm & late[m]).mean())

    best = min(candidates, key=lambda m: (joint(m), float(late[m].mean()), m))
    return Hedge(
        backup_mode=best,
        leave_by_ts=leave_by_ts[best],
        p_both_late=joint(best),
        p_late_main=float(lm.mean()),
        p_late_backup=float(late[best].mean()),
        both_late_scenarios=int((lm & late[best]).sum()),
        total_scenarios=int(lm.size),
    )
