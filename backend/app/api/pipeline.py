"""Application service: request -> adapters -> decision layer -> API models.

Routers stay thin; the layer rules still hold (adapters fetch, the decision layer decides, this file only wires
them together and turns results into the public contract)."""

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from app.adapters.fallback import estimate_route, neutral_weather
from app.api.schemas import (
    AccessibilityOut,
    ArrivalQuantiles,
    CliffPoint,
    ExplanationOut,
    Headline,
    HedgeOut,
    OptionOut,
    RecommendationData,
    RecommendationRequest,
    RescoreRequest,
    SourceInfo,
)
from app.api.services import Services
from app.core import clock
from app.core.resilience import UpstreamError
from app.core.seed import seed_from
from app.core.types import SourceMeta
from app.decision.engine import Decision, OptionResult, Problem, RouteInfo, Simulation, decide, simulate_all
from app.decision.explain import explain

DEGRADED_CODES = {"WEATHER_UNAVAILABLE", "WEATHER_STALE", "ROUTE_ESTIMATED"}
STALE_AFTER_S = 30 * 60
MOCK_SOURCES = {
    "mock-rail": "Simulated data",
    "mock-fares": "Simulated data",
    "mock-accessibility": "Simulated data",
    "mock-emissions": "Placeholder values, replace with official factors",
}
REGISTRY = [
    SourceInfo(
        id="open-meteo-ensemble",
        kind="live",
        role="Weather scenarios (51 ensemble members)",
        licence="Non-commercial use",
        attribution="Weather data by Open-Meteo.com",
    ),
    SourceInfo(
        id="osrm",
        kind="live",
        role="Routing for car, bike and foot",
        licence="ODbL (OpenStreetMap contributors)",
        attribution="Routing by FOSSGIS OSRM; map data (c) OpenStreetMap contributors",
    ),
    SourceInfo(
        id="open-meteo-geocoding",
        kind="live",
        role="Place search",
        licence="Non-commercial use",
        attribution="Geocoding by Open-Meteo.com",
    ),
    *[
        SourceInfo(id=sid, kind="mock", role=role, licence=lic)
        for sid, role, lic in [
            ("mock-rail", "Train timetable and delays", MOCK_SOURCES["mock-rail"]),
            ("mock-fares", "Fares and running costs", MOCK_SOURCES["mock-fares"]),
            ("mock-accessibility", "Step-free access and effort", MOCK_SOURCES["mock-accessibility"]),
            ("mock-emissions", "Carbon per km", MOCK_SOURCES["mock-emissions"]),
        ]
    ],
]


@dataclass
class Record:
    id: str
    request: RecommendationRequest
    sim: Simulation
    problem: Problem
    decision: Decision
    warnings: list[dict[str, str]]
    sources: list[SourceMeta]
    seed: int
    degraded: bool
    weather_id: str
    route_ids: dict[str, str]


def to_problem(req: RecommendationRequest, deadline_ts: int) -> Problem:
    c = req.constraints
    return Problem(
        deadline_ts=deadline_ts,
        confidence=req.confidence,
        weights=req.weights.model_dump(),
        step_free=c.step_free,
        max_walk_m=c.max_walk_m,
        has_luggage=c.has_luggage,
        has_car=c.has_car,
        hedge=req.options.hedge,
    )


def _dedupe(sources: list[SourceMeta]) -> list[SourceMeta]:
    seen: set[tuple[str, str]] = set()
    out = []
    for s in sources:
        if (s.id, s.kind) not in seen:
            seen.add((s.id, s.kind))
            out.append(s)
    return out


async def build(req: RecommendationRequest, services: Services) -> Record:
    now = clock.now()
    deadline_ts = int(req.arrive_by.timestamp())
    warnings: list[dict[str, str]] = []
    sources: list[SourceMeta] = []

    weather_failed = False
    try:
        w = await services.weather.fetch(req.origin.lat, req.origin.lon)
        weather = w.data
        sources.append(w.meta)
        weather_id = w.meta.id
        if w.meta.age_s > STALE_AFTER_S:
            minutes = w.meta.age_s // 60
            msg = f"Weather forecast is {minutes} minutes old. Showing the last good forecast."
            warnings.append({"code": "WEATHER_STALE", "message": msg})
    except UpstreamError:
        weather_failed = True
        weather = neutral_weather(deadline_ts)
        weather_id = "no-weather"
        msg = "Weather forecast unavailable. Showing travel times without weather risk. Try again in a minute."
        warnings.append({"code": "WEATHER_UNAVAILABLE", "message": msg})
        sources.append(SourceMeta(id=weather_id, kind="estimated", fetched_at=now, age_s=0, licence="Not applicable"))

    origin, dest = (req.origin.lat, req.origin.lon), (req.destination.lat, req.destination.lon)
    routes: dict[str, RouteInfo] = {}
    route_ids: dict[str, str] = {}
    failed = 0
    for mode, profile in (("walk", "foot"), ("bike", "bike"), ("drive", "car")):
        try:
            r = await services.routing.fetch(profile, origin, dest)  # type: ignore[arg-type]
            route, meta = r.data, r.meta
        except UpstreamError:
            failed += 1
            route = estimate_route(profile, origin, dest)
            meta = SourceMeta(id="osrm-estimate", kind="estimated", fetched_at=now, age_s=0, licence="Not applicable")
            msg = f"Routing unavailable for {mode}. Using a straight-line estimate."
            warnings.append({"code": "ROUTE_ESTIMATED", "message": msg})
        sources.append(meta)
        route_ids[mode] = meta.id
        routes[mode] = RouteInfo(route.distance_m, route.duration_s, route.bearing_deg)

    if weather_failed and failed == 3:
        raise UpstreamError("every live data source is unavailable")

    if req.options.stress_test:
        warnings.append({"code": "STRESS_TEST_UNAVAILABLE", "message": "Worst-10% planning is not available yet."})

    seed = seed_from(
        {
            "o": [round(req.origin.lat, 4), round(req.origin.lon, 4)],
            "d": [round(req.destination.lat, 4), round(req.destination.lon, 4)],
            "t": deadline_ts,
        }
    )
    sim = simulate_all(routes, weather, deadline_ts, seed, services.cfg, services.data)
    problem = to_problem(req, deadline_ts)
    for sid, lic in MOCK_SOURCES.items():
        sources.append(SourceMeta(id=sid, kind="mock", fetched_at=now, age_s=0, licence=lic))
    return Record(
        id="rec_" + uuid.uuid4().hex[:10],
        request=req,
        sim=sim,
        problem=problem,
        decision=decide(sim, problem),
        warnings=warnings,
        sources=_dedupe(sources),
        seed=seed,
        degraded=any(w["code"] in DEGRADED_CODES for w in warnings),
        weather_id=weather_id,
        route_ids=route_ids,
    )


def rescore(rec: Record, body: RescoreRequest) -> Record:
    """Re-decide from the stored simulation. No provider is called."""
    p = rec.problem
    if body.confidence is not None:
        p = replace(p, confidence=body.confidence)
    if body.weights is not None:
        p = replace(p, weights=body.weights.model_dump())
    if body.constraints is not None:
        c = body.constraints
        p = replace(p, step_free=c.step_free, max_walk_m=c.max_walk_m, has_luggage=c.has_luggage, has_car=c.has_car)
    if body.options is not None:
        p = replace(p, hedge=body.options.hedge)
    return replace(rec, problem=p, decision=decide(rec.sim, p))


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def _provenance(mode: str, rec: Record) -> list[str]:
    ids = [rec.weather_id, rec.route_ids["drive" if mode == "train" else mode]]
    if mode == "train":
        ids.append("mock-rail")
    if mode in ("train", "drive"):
        ids.append("mock-fares")
    return [*ids, "mock-emissions", "mock-accessibility"]


def _option_out(o: OptionResult, rec: Record) -> OptionOut:
    s, f, p = o.summary, o.facts, rec.problem
    access = f.effort * (f.luggage_factor if p.has_luggage else 1.0)
    return OptionOut(
        mode=o.mode,  # type: ignore[arg-type]
        rank=o.rank,
        score=o.score,
        feasible=o.feasible,
        infeasible_reason=o.infeasible_reason,
        leave_by=_dt(s.leave_by_ts) if o.feasible and s.leave_by_ts is not None else None,
        p_on_time=s.p_on_time,
        on_time_scenarios=s.on_time_scenarios,
        total_scenarios=s.total_scenarios,
        arrival=ArrivalQuantiles(p05=_dt(s.arrival_p05), p50=_dt(s.arrival_p50), p95=_dt(s.arrival_p95)),
        journey_at_risk_min=s.journey_at_risk_min,
        cost_gbp=f.cost_gbp,
        co2e_kg=f.co2e_kg,
        accessibility=AccessibilityOut(feasible=f.step_free or not p.step_free, score=min(1.0, max(0.0, access))),
        cliff=[CliffPoint(leave=_dt(t), p_on_time=x) for t, x in s.cliff],
        scenario_arrivals=[_dt(t) for t in s.scenario_arrivals],
        provenance=_provenance(o.mode, rec),
    )


def to_data(rec: Record) -> RecommendationData:
    d = rec.decision
    ex = explain(d)
    win = d.winner
    headline = None
    if win is not None and win.summary.leave_by_ts is not None:
        s = win.summary
        headline = Headline(
            mode=win.mode,  # type: ignore[arg-type]
            leave_at=_dt(s.leave_by_ts),
            p_on_time=s.p_on_time,
            on_time_scenarios=s.on_time_scenarios,
            total_scenarios=s.total_scenarios,
        )
    hedge = None
    if d.hedge is not None:
        h = d.hedge
        hedge = HedgeOut(
            backup_mode=h.backup_mode,  # type: ignore[arg-type]
            leave_at=_dt(h.leave_by_ts),
            p_both_late=h.p_both_late,
            both_late_scenarios=h.both_late_scenarios,
            total_scenarios=h.total_scenarios,
            reason=ex.hedge,
        )
    return RecommendationData(
        recommendation_id=rec.id,
        headline=headline,
        options=[_option_out(o, rec) for o in d.options],
        hedge=hedge,
        explanation=ExplanationOut(because=ex.because, tradeoffs=ex.tradeoffs, flip_points=ex.flip_points),
    )


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def make_ics(rec: Record, opt: OptionResult) -> str:
    def stamp(ts: int) -> str:
        return _dt(ts).strftime("%Y%m%dT%H%M%SZ")

    assert opt.summary.leave_by_ts is not None
    s = opt.summary
    summary = _esc(f"Leave for {rec.request.destination.label} ({opt.mode})")
    description = _esc(
        f"On time in {s.on_time_scenarios} of {s.total_scenarios} simulated mornings. Rail data is mock."
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LeaveBy//EN",
        "BEGIN:VEVENT",
        f"UID:{rec.id}-{opt.mode}@leaveby",
        f"DTSTAMP:{stamp(int(clock.now().timestamp()))}",
        f"DTSTART:{stamp(s.leave_by_ts)}",
        f"DTEND:{stamp(rec.problem.deadline_ts)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Time to leave",
        "TRIGGER:-PT10M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def public_meta(rec: Record) -> dict[str, Any]:
    return {
        "seed": rec.seed,
        "degraded": rec.degraded,
        "warnings": rec.warnings,
        "sources": [s.model_dump(mode="json") for s in rec.sources],
    }
