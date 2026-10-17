"""Turn a simulation into the numbers the user sees (blueprint 5.5)."""

from dataclasses import dataclass

import numpy as np

from app.decision.simulate import SimResult


@dataclass(frozen=True)
class ModeSummary:
    mode: str
    feasible: bool  # can this mode reach the confidence level at any simulated departure?
    leave_by_ts: int | None  # latest departure meeting the confidence; None if infeasible
    p_on_time: float  # at the reference departure (leave_by, or the best one if infeasible)
    journey_at_risk_min: float  # quantile_c(duration) - median(duration), minutes
    arrival_p05: int
    arrival_p50: int
    arrival_p95: int
    on_time_scenarios: int  # counted over every scenario (ensemble member x noise draw), so it agrees with p_on_time.
    total_scenarios: int
    cliff: list[tuple[int, float]]  # (departure ts, P(on time)) for the whole grid
    scenario_arrivals: list[int]  # one arrival ts per ensemble member, for the raincloud dots
    ref_index: int


def p_on_time(sim: SimResult, deadline_ts: int) -> np.ndarray:
    """P(arrive by the deadline) for every departure in the grid, shape (D,)."""
    return (sim.arrivals <= deadline_ts).mean(axis=(1, 2))


def leave_by_index(p: np.ndarray, confidence: float) -> int | None:
    ok = np.flatnonzero(p >= confidence)
    return int(ok[-1]) if ok.size else None


def journey_at_risk_s(durations: np.ndarray, confidence: float) -> float:
    return float(np.quantile(durations, confidence) - np.median(durations))


def summarise(sim: SimResult, deadline_ts: int, confidence: float) -> ModeSummary:
    p = p_on_time(sim, deadline_ts)
    idx = leave_by_index(p, confidence)
    feasible = idx is not None
    ref = idx if idx is not None else int(np.argmax(p))
    arr = sim.arrivals[ref]  # (M, K)
    q05, q50, q95 = np.quantile(arr.ravel(), [0.05, 0.5, 0.95])
    dots = arr[:, 0]
    return ModeSummary(
        mode=sim.mode,
        feasible=feasible,
        leave_by_ts=int(sim.departures[idx]) if idx is not None else None,
        p_on_time=float(p[ref]),
        journey_at_risk_min=journey_at_risk_s(sim.durations[ref].ravel(), confidence) / 60.0,
        arrival_p05=int(round(q05)),
        arrival_p50=int(round(q50)),
        arrival_p95=int(round(q95)),
        on_time_scenarios=int((arr <= deadline_ts).sum()),
        total_scenarios=int(arr.size),
        cliff=[(int(t), float(x)) for t, x in zip(sim.departures, p, strict=True)],
        scenario_arrivals=[int(round(x)) for x in dots],
        ref_index=ref,
    )
