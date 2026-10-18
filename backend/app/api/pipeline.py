"""Application service: request -> adapters -> decision layer -> API models.

Routers stay thin; the layer rules still hold (adapters fetch, the decision layer decides, this file only wires
them together and turns results into the public contract)."""

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.adapters.fallback import estimate_route, neutral_weather
from app.adapters.weather import WeatherEnsemble
from app.api.schemas import (
    AccessibilityOut,
    ArrivalQuantiles,
    CliffPoint,
    ExplanationOut,
    Headline,
    HedgeOut,
    IncidentsOut,
    OptionOut,
    RecommendationData,
    RecommendationRequest,
    RescoreRequest,
    RouteOut,
    SourceInfo,
    TrafficOut,
    TrainService,
    WeatherOut,
    WeatherPointOut,
)
from app.api.services import Services
from app.core import clock
from app.core.config import ModelConfig
from app.core.resilience import UpstreamError
from app.core.seed import seed_from
from app.core.types import SourceMeta
from app.decision.engine import Decision, OptionResult, Problem, RouteInfo, Simulation, decide, simulate_all
from app.decision.explain import explain
from app.decision.rail_timetable import OutOfRange, lookup
from app.decision.weather_story import dry_weather, extra_minutes, members_at, point, tips, train_late_risk

TIMETABLE_ATTRIBUTION = "Timetable data: Rail Delivery Group (DTD feed), via planarnetwork/gb-transit"
DEGRADED_CODES = {"WEATHER_UNAVAILABLE", "WEATHER_STALE", "ROUTE_ESTIMATED"}
STALE_AFTER_S = 30 * 60
MOCK_SOURCES = {
    "mock-rail": "Simulated data",
    "mock-rail-delays": "Simulated, calibrated to published punctuality",
    "mock-fares": "Simulated data",
    "mock-accessibility": "Simulated data",
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
    SourceInfo(
        id="tomtom-live",
        kind="live",
        role="Car travel time with live traffic, and incidents near the route (trips leaving within 2 hours)",
        licence="TomTom developer terms",
        attribution="Traffic by TomTom",
    ),
    SourceInfo(
        id="tomtom-predicted",
        kind="live",
        role="Car travel time with TomTom's predicted traffic for the departure time (later trips)",
        licence="TomTom developer terms",
        attribution="Traffic by TomTom",
    ),
    SourceInfo(
        id="desnz-ghg-2026",
        kind="static",
        role="Carbon per km (UK Government GHG conversion factors 2026)",
        licence="Open Government Licence v3.0",
        attribution="Contains public sector information licensed under the Open Government Licence v3.0 (DESNZ)",
    ),
    SourceInfo(
        id="rdg-timetable",
        kind="static",
        role="Train timetable (real scheduled trains, static file)",
        licence="Rail Delivery Group open data",
        attribution=TIMETABLE_ATTRIBUTION,
    ),
    *[
        SourceInfo(id=sid, kind="mock", role=role, licence=lic)
        for sid, role, lic in [
            ("mock-rail", "Trains where the real timetable does not reach", MOCK_SOURCES["mock-rail"]),
            ("mock-rail-delays", "Train delays", MOCK_SOURCES["mock-rail-delays"]),
            ("simulated-incident", "Demo accident on the car route (only when switched on)", "Demo only"),
            ("mock-fares", "Fares and running costs", MOCK_SOURCES["mock-fares"]),
            ("mock-accessibility", "Step-free access and effort", MOCK_SOURCES["mock-accessibility"]),
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
    traffic: TrafficOut | None = None
    car_line: list[tuple[float, float]] | None = None  # (lat, lon), simplified, for the map
    weather: WeatherEnsemble | None = None  # the real forecast (None when it failed), for the weather story
    dry_sim: Simulation | None = None  # the same trip on a dry, calm morning with the same seeds


def to_problem(req: RecommendationRequest, deadline_ts: int) -> Problem:
    c = req.constraints
    return Problem(
        deadline_ts=deadline_ts,
        confidence=req.confidence,
        weights=req.weights.model_dump(),
        step_free=c.step_free,
        max_walk_m=c.max_walk_m,
        max_bike_m=c.max_bike_m,
        has_luggage=c.has_luggage,
        has_car=c.has_car,
        hedge=req.options.hedge,
    )


def as_recorded(s: SourceMeta, recorded_at: datetime) -> SourceMeta:
    if s.kind not in ("live", "cached"):
        return s
    age = int((clock.now() - recorded_at).total_seconds())
    return s.model_copy(update={"kind": "recorded", "fetched_at": recorded_at, "age_s": max(age, 0)})


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
    car_line: list[tuple[float, float]] | None = None
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
        if mode == "drive":
            car_line = _thin([(lat, lon) for lon, lat in route.geometry])

    if weather_failed and failed == 3:
        raise UpstreamError("every live data source is unavailable")

    traffic = await _traffic(req, services, routes, route_ids, sources, warnings, deadline_ts, now)

    if req.options.stress_test:
        warnings.append({"code": "STRESS_TEST_UNAVAILABLE", "message": "Worst-10% planning is not available yet."})

    seed = seed_from(
        {
            "o": [round(req.origin.lat, 4), round(req.origin.lon, 4)],
            "d": [round(req.destination.lat, 4), round(req.destination.lon, 4)],
            "t": deadline_ts,
        }
    )
    schedule = None
    if services.timetable is not None:
        try:
            schedule = lookup(services.timetable, origin, dest, deadline_ts, services.cfg)
        except OutOfRange:
            tt = services.timetable
            msg = f"Real train times cover {tt.valid_from} to {tt.valid_to}. Using simulated trains for this date."
            warnings.append({"code": "TIMETABLE_OUT_OF_RANGE", "message": msg})
    sim = simulate_all(routes, weather, deadline_ts, seed, services.cfg, services.data, schedule)
    dry_sim = None
    if not weather_failed:
        dry_sim = simulate_all(routes, dry_weather(weather), deadline_ts, seed, services.cfg, services.data, schedule)
    problem = to_problem(req, deadline_ts)
    licence = services.cfg.emissions.licence
    sources.append(SourceMeta(id="desnz-ghg-2026", kind="static", fetched_at=now, age_s=0, licence=licence))
    if schedule is not None:
        assert services.timetable is not None
        sources.append(
            SourceMeta(
                id="rdg-timetable",
                kind="static",
                fetched_at=now,
                age_s=0,
                licence=f"Rail Delivery Group open data, feed {services.timetable.release}",
                attribution=TIMETABLE_ATTRIBUTION,
            )
        )
    if services.recorded_at is not None:  # offline demo mode: nothing here is live, whatever the adapters say
        sources = [as_recorded(s, services.recorded_at) for s in sources]
    unused = "mock-rail" if schedule is not None else "mock-rail-delays"
    for sid, lic in MOCK_SOURCES.items():
        if sid != unused:
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
        traffic=traffic,
        car_line=car_line,
        weather=None if weather_failed else weather,
        dry_sim=dry_sim,
    )


def _thin(points: list[tuple[float, float]], max_points: int = 200) -> list[tuple[float, float]]:
    """Keep every k-th point (and the last) so the map line stays small."""
    if len(points) <= max_points:
        return points
    step = -(-len(points) // max_points)
    return [*points[::step][: max_points - 1], points[-1]]


async def _traffic(
    req: RecommendationRequest,
    services: Services,
    routes: dict[str, RouteInfo],
    route_ids: dict[str, str],
    sources: list[SourceMeta],
    warnings: list[dict[str, str]],
    deadline_ts: int,
    now: datetime,
) -> TrafficOut | None:
    """Replace the free-flow car time with TomTom's traffic time (live for trips leaving soon, predicted for
    later ones), report incidents for live trips, and apply the demo accident if asked. Mutates routes."""
    cfg = services.cfg.traffic
    drive = routes["drive"]
    free_flow_s = drive.duration_s
    basis = "free-flow"
    incidents: IncidentsOut | None = None
    if services.traffic is not None:
        depart_ts = int(deadline_ts - free_flow_s * 1.3)  # a rough leave time, good enough for a 15 min bucket
        live = depart_ts - now.timestamp() < cfg.live_window_h * 3600
        origin, dest = (req.origin.lat, req.origin.lon), (req.destination.lat, req.destination.lon)
        try:
            r = await services.traffic.route(origin, dest, depart_ts, live)
            drive = RouteInfo(r.data.distance_m, r.data.duration_s, drive.bearing_deg)
            basis = r.data.basis
            route_ids["drive"] = r.meta.id
            sources.append(r.meta)
            if live:
                found = await services.traffic.incidents(r.data.bbox)
                if found is not None and found.count:
                    incidents = IncidentsOut(
                        count=found.count,
                        worst_delay_min=found.worst_delay_s / 60,
                        description=found.description,
                        simulated=False,
                    )
        except UpstreamError:
            msg = "Traffic data unavailable. Car times use free-flow routing without traffic."
            warnings.append({"code": "TRAFFIC_UNAVAILABLE", "message": msg})
    if req.options.simulate_incident:
        delay_s = cfg.simulated_incident_delay_min * 60
        drive = RouteInfo(drive.distance_m, drive.duration_s + delay_s, drive.bearing_deg)
        incidents = IncidentsOut(
            count=1,
            worst_delay_min=delay_s / 60,
            description="Simulated accident on your route (demo)",
            simulated=True,
        )
        sources.append(SourceMeta(id="simulated-incident", kind="mock", fetched_at=now, age_s=0, licence="Demo only"))
    routes["drive"] = drive
    if services.traffic is None and not req.options.simulate_incident:
        return None  # no traffic data configured: the response stays as it always was
    return TrafficOut(basis=basis, car_min=drive.duration_s / 60, free_flow_min=free_flow_s / 60, incidents=incidents)


def rescore(rec: Record, body: RescoreRequest) -> Record:
    """Re-decide from the stored simulation. No provider is called."""
    p = rec.problem
    if body.confidence is not None:
        p = replace(p, confidence=body.confidence)
    if body.weights is not None:
        p = replace(p, weights=body.weights.model_dump())
    if body.constraints is not None:
        c = body.constraints
        p = replace(
            p,
            step_free=c.step_free,
            max_walk_m=c.max_walk_m,
            max_bike_m=c.max_bike_m,
            has_luggage=c.has_luggage,
            has_car=c.has_car,
        )
    if body.options is not None:
        p = replace(p, hedge=body.options.hedge)
    return replace(rec, problem=p, decision=decide(rec.sim, p))


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def _provenance(mode: str, rec: Record) -> list[str]:
    ids = [rec.weather_id, rec.route_ids["drive" if mode == "train" else mode]]
    if mode == "train":
        real = rec.sim.train_services is not None or rec.sim.train_no_service
        ids += ["rdg-timetable", "mock-rail-delays"] if real else ["mock-rail"]
    if mode == "drive" and rec.traffic and rec.traffic.incidents and rec.traffic.incidents.simulated:
        ids.append("simulated-incident")
    if mode in ("train", "drive"):
        ids.append("mock-fares")
    return [*ids, "desnz-ghg-2026", "mock-accessibility"]


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
        service=_service(o, rec),
    )


def _service(o: OptionResult, rec: Record) -> TrainService | None:
    """The real train behind the leave-by time: the one simulated at the reference departure."""
    if o.mode != "train" or not o.feasible or rec.sim.train_services is None:
        return None
    run = rec.sim.train_services[o.summary.ref_index]
    return TrainService(
        depart_at=_dt(run.depart_ts),
        arrive_at=_dt(run.arrive_ts),
        operator=run.operator,
        headsign=run.headsign,
        from_station=run.from_name,
        to_station=run.to_name,
        from_coord=run.from_coord,
        to_coord=run.to_coord,
    )


def _weather_out(rec: Record, cfg: ModelConfig) -> WeatherOut | None:
    if rec.weather is None or rec.dry_sim is None:
        return None
    d, w = rec.decision, rec.weather
    deadline = rec.problem.deadline_ts
    leave = d.winner.summary.leave_by_ts if d.winner and d.winner.summary.leave_by_ts else deadline - 3600
    dep = point(w, leave)
    extra = extra_minutes(d, decide(rec.dry_sim, rec.problem))
    calm, now = train_late_risk(w, leave, cfg)
    return WeatherOut(
        departure=WeatherPointOut(**{**dep.__dict__, "at": _dt(dep.at)}),
        arrival=WeatherPointOut(**{**point(w, deadline).__dict__, "at": _dt(deadline)}),
        extra_min=extra,
        train_late_over_5min=(calm, now) if "train" in {o.mode for o in d.options if o.feasible} else None,
        members_at_departure=members_at(w, leave),
        tips=tips(w, dep, leave, deadline, extra, d, cfg),
    )


def to_data(rec: Record, cfg: ModelConfig) -> RecommendationData:
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
        traffic=rec.traffic,
        weather=_weather_out(rec, cfg),
        route=RouteOut(
            origin=(rec.request.origin.lat, rec.request.origin.lon),
            destination=(rec.request.destination.lat, rec.request.destination.lon),
            car_line=rec.car_line,
        ),
    )


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def _chance(on_time: int, total: int) -> str:
    """'97%', '>99%' or '100%': never round a chance up to certainty."""
    if on_time == total:
        return "100%"
    p = 100 * on_time / total
    return ">99%" if p > 99 else f"{round(p)}%"


def make_ics(rec: Record, opt: OptionResult, timezone: str) -> str:
    def stamp(ts: int) -> str:
        return _dt(ts).strftime("%Y%m%dT%H%M%SZ")

    def hm(ts: int) -> str:
        return _dt(ts).astimezone(ZoneInfo(timezone)).strftime("%H:%M")

    assert opt.summary.leave_by_ts is not None
    s = opt.summary
    summary = _esc(f"Leave for {rec.request.destination.label} ({opt.mode})")
    by = {"walk": "on foot", "bike": "by bike", "drive": "by car", "train": "by train"}
    plan = [f"Leave at {hm(s.leave_by_ts)} {by[opt.mode]} to reach {rec.request.destination.label}."]
    svc = _service(opt, rec)
    if svc is not None:
        dep, arr = int(svc.depart_at.timestamp()), int(svc.arrive_at.timestamp())
        plan.append(f"Catch the {hm(dep)} {svc.operator} from {svc.from_station}, arrives {svc.to_station} {hm(arr)}.")
    chance = _chance(s.on_time_scenarios, s.total_scenarios)
    plan.append(f"{chance} chance you arrive on time, from the forecast for your route.")
    h = rec.decision.hedge
    if h is not None and opt is rec.decision.winner:
        plan.append(f"Backup: leave at {hm(h.leave_by_ts)} {by[h.backup_mode]}.")
    plan.append("Delays, fares and access are modelled; see the app's sources for what is real.")
    description = "\\n".join(_esc(p) for p in plan)  # an escaped newline inside an iCalendar text value
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
