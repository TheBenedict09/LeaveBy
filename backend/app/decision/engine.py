"""Orchestrates the decision layer: simulate every mode once, then decide (cheap, re-runnable).

simulate_all is the expensive step and its result can be stored; decide() is what the rescore endpoint
re-runs when the user moves the confidence slider or the priority weights (blueprint 4.2)."""

from dataclasses import dataclass, field

from app.adapters.weather import WeatherEnsemble
from app.core.config import ModelConfig
from app.core.mockdata import MockData
from app.decision.hedge import Hedge, choose_hedge
from app.decision.rail_mock import make_rail_noise, simulate_train, train_departures
from app.decision.scoring import (
    FlipPoint,
    composite,
    flip_points,
    normalise_criteria,
    normalise_weights,
    rank_modes,
)
from app.decision.simulate import SimResult, departure_grid, make_noise, simulate
from app.decision.summarise import ModeSummary, summarise

MODES = ("walk", "bike", "drive", "train")


@dataclass(frozen=True)
class RouteInfo:
    """Decision-layer view of a route; adapters convert their own types into this."""

    distance_m: float
    duration_s: float
    bearing_deg: float


@dataclass(frozen=True)
class ModeFacts:
    distance_m: float
    cost_gbp: float
    co2e_kg: float
    effort: float
    step_free: bool
    luggage_factor: float


@dataclass(frozen=True)
class Simulation:
    deadline_ts: int
    seed: int
    n_members: int
    n_draws: int
    sims: dict[str, SimResult]
    facts: dict[str, ModeFacts]


@dataclass(frozen=True)
class Problem:
    deadline_ts: int
    confidence: float
    weights: dict[str, float]
    step_free: bool = False
    max_walk_m: int = 1200
    max_bike_m: int = 25000
    has_luggage: bool = False
    has_car: bool = False
    hedge: bool = True


@dataclass(frozen=True)
class OptionResult:
    mode: str
    summary: ModeSummary
    facts: ModeFacts
    feasible: bool
    infeasible_reason: str | None
    lead_time_min: float | None  # how long before the deadline you must leave to be c-sure
    score: float | None
    rank: int | None


@dataclass(frozen=True)
class Decision:
    confidence: float
    weights: dict[str, float]
    options: list[OptionResult]  # ranked feasible options first, then infeasible ones
    winner: OptionResult | None
    hedge: Hedge | None
    flips: list[FlipPoint] = field(default_factory=list)


def _facts(mode: str, distance_m: float, data: MockData) -> ModeFacts:
    km = distance_m / 1000.0
    if mode == "train":
        cost = data.fares.train_base_gbp + data.fares.train_per_km_gbp * km
    elif mode == "drive":
        cost = data.fares.drive_per_km_gbp * km
    else:
        cost = 0.0
    a = data.accessibility[mode]
    return ModeFacts(distance_m, cost, data.emissions_kg_per_km[mode] * km, a.effort, a.step_free, a.luggage_factor)


def simulate_all(
    routes: dict[str, RouteInfo],
    weather: WeatherEnsemble,
    deadline_ts: int,
    seed: int,
    cfg: ModelConfig,
    data: MockData,
) -> Simulation:
    """routes needs walk, bike and drive. Rail (mock) reuses the drive distance as its distance."""
    n_members, n_draws = weather.n_members, cfg.noise.n_draws
    z = make_noise(seed, n_members, n_draws)  # shared by every mode
    sims: dict[str, SimResult] = {}
    facts: dict[str, ModeFacts] = {}
    for mode in ("walk", "bike", "drive"):
        r = routes[mode]
        deps = departure_grid(deadline_ts, r.duration_s, cfg)
        sims[mode] = simulate(mode, r.duration_s, r.bearing_deg, weather, deps, z, cfg)
        facts[mode] = _facts(mode, r.distance_m, data)
    rail_m = routes["drive"].distance_m
    deps = train_departures(deadline_ts, rail_m, cfg)
    sims["train"] = simulate_train(rail_m, weather, deps, make_rail_noise(seed, n_members, n_draws), cfg)
    facts["train"] = _facts("train", rail_m, data)
    return Simulation(deadline_ts, seed, n_members, n_draws, sims, facts)


def _infeasible_reason(mode: str, s: ModeSummary, f: ModeFacts, p: Problem) -> str | None:
    """Hard constraints first (blueprint 5.6); the confidence test comes last."""
    if mode == "drive" and not p.has_car:
        return "No car available"
    if mode == "walk" and f.distance_m > p.max_walk_m:
        return "Further than your walking limit"
    if mode == "bike" and f.distance_m > p.max_bike_m:
        return "Further than your cycling limit"
    if p.step_free and not f.step_free:
        return "No step-free route"
    if not s.feasible:
        return f"Cannot reach with {round(p.confidence * 100)}% confidence by the deadline"
    return None


def _criteria(s: ModeSummary, f: ModeFacts, p: Problem) -> dict[str, float]:
    assert s.leave_by_ts is not None
    return {
        "time": (p.deadline_ts - s.leave_by_ts) / 60.0,
        "cost": f.cost_gbp,
        "carbon": f.co2e_kg,
        "accessibility": f.effort * (f.luggage_factor if p.has_luggage else 1.0),
    }


def decide(sim: Simulation, problem: Problem) -> Decision:
    w = normalise_weights(problem.weights)
    summaries = {m: summarise(sim.sims[m], sim.deadline_ts, problem.confidence) for m in MODES}
    reasons = {m: _infeasible_reason(m, summaries[m], sim.facts[m], problem) for m in MODES}
    feasible = [m for m in MODES if reasons[m] is None]

    raw = {m: _criteria(summaries[m], sim.facts[m], problem) for m in feasible}
    norm = normalise_criteria(raw) if feasible else {}
    scores = composite(norm, w) if feasible else {}
    p_map = {m: summaries[m].p_on_time for m in feasible}
    cost_map = {m: sim.facts[m].cost_gbp for m in feasible}
    order = rank_modes(scores, p_map, cost_map) if feasible else []

    def make(mode: str, rank: int | None) -> OptionResult:
        return OptionResult(
            mode=mode,
            summary=summaries[mode],
            facts=sim.facts[mode],
            feasible=reasons[mode] is None,
            infeasible_reason=reasons[mode],
            lead_time_min=raw[mode]["time"] if mode in raw else None,
            score=scores.get(mode),
            rank=rank,
        )

    options = [make(m, i + 1) for i, m in enumerate(order)] + [make(m, None) for m in MODES if m not in order]
    winner = options[0] if order else None

    hedge = None
    if problem.hedge and len(order) >= 2:
        late = {m: sim.sims[m].arrivals[summaries[m].ref_index] > sim.deadline_ts for m in order}
        leave = {m: int(summaries[m].leave_by_ts) for m in order}  # type: ignore[arg-type]
        hedge = choose_hedge(order[0], late, leave)

    flips = flip_points(norm, w, p_map, cost_map) if len(order) >= 2 else []
    return Decision(problem.confidence, w, options, winner, hedge, flips)
