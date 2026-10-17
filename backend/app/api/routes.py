from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.api import envelope, pipeline
from app.api.schemas import (
    Envelope,
    GeocodeData,
    Mode,
    Place,
    RecommendationData,
    RecommendationRequest,
    RescoreRequest,
    SourcesData,
)
from app.api.services import Services, get_services

router = APIRouter()


def _ok(request: Request, data: Any, **meta: Any) -> dict[str, Any]:
    payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
    return {"ok": True, "data": payload, "meta": envelope.meta(request.state.request_id, **meta)}


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
def readyz(services: Services = Depends(get_services)) -> dict[str, str]:  # noqa: B008
    # Config and mock data are loaded when Services is built; if they were broken the app would not have started.
    return {"status": "ready" if services.cfg and services.data else "not ready"}


@router.post("/v1/recommendations", response_model=Envelope[RecommendationData], tags=["recommendations"])
async def create_recommendation(
    body: RecommendationRequest,
    request: Request,
    services: Services = Depends(get_services),  # noqa: B008
) -> dict[str, Any]:
    rec = await pipeline.build(body, services)
    services.store.put(rec)
    return _ok(request, pipeline.to_data(rec), **pipeline.public_meta(rec))


@router.post(
    "/v1/recommendations/{rec_id}/rescore", response_model=Envelope[RecommendationData], tags=["recommendations"]
)
async def rescore_recommendation(
    rec_id: str,
    body: RescoreRequest,
    request: Request,
    services: Services = Depends(get_services),  # noqa: B008
) -> dict[str, Any]:
    """New confidence, priorities or constraints, answered from the stored simulation. No provider is called."""
    rec = services.store.get(rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Unknown recommendation id")
    new = pipeline.rescore(rec, body)
    services.store.put(new)
    return _ok(request, pipeline.to_data(new), **pipeline.public_meta(new))


@router.get("/v1/recommendations/{rec_id}/calendar.ics", tags=["recommendations"])
async def calendar(
    rec_id: str,
    mode: Mode,
    services: Services = Depends(get_services),  # noqa: B008
) -> Response:
    rec = services.store.get(rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Unknown recommendation id")
    opt = next((o for o in rec.decision.options if o.mode == mode and o.feasible), None)
    if opt is None or opt.summary.leave_by_ts is None:
        raise HTTPException(status_code=404, detail=f"No leave-by time for {mode}")
    return Response(content=pipeline.make_ics(rec, opt), media_type="text/calendar")


@router.get("/v1/geocode", response_model=Envelope[GeocodeData], tags=["places"])
async def geocode(
    request: Request,
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=10),
    services: Services = Depends(get_services),  # noqa: B008
) -> dict[str, Any]:
    q = q.strip()
    if len(q) < 2 or any(ord(c) < 32 for c in q):
        raise HTTPException(status_code=422, detail="Search text must be 2 to 100 plain characters")
    res = await services.geocode.fetch(q, limit)
    data = GeocodeData(places=[Place(label=p.label, lat=p.lat, lon=p.lon) for p in res.data])
    fallback = res.meta.kind == "estimated"
    warnings = (
        [{"code": "GEOCODER_FALLBACK", "message": "Place search is unavailable. Pick a city or enter coordinates."}]
        if fallback
        else []
    )
    return _ok(request, data, degraded=fallback, warnings=warnings, sources=[res.meta.model_dump(mode="json")])


@router.get("/v1/sources", response_model=Envelope[SourcesData], tags=["transparency"])
async def sources(request: Request) -> dict[str, Any]:
    return _ok(request, SourcesData(sources=pipeline.REGISTRY))


@router.get("/v1/assumptions", response_model=Envelope[dict[str, Any]], tags=["transparency"])
async def assumptions(request: Request, services: Services = Depends(get_services)) -> dict[str, Any]:  # noqa: B008
    """Every coefficient the model uses, the mock data tables and the real timetable's validity. Nothing is hidden."""
    tt = services.timetable
    timetable = None
    if tt is not None:
        timetable = {"source": tt.source, "release": tt.release, "valid_from": tt.valid_from, "valid_to": tt.valid_to}
        timetable["stations"] = sorted(s.name for s in tt.stations.values())
    payload = {"model": services.cfg.model_dump(), "mock_data": services.data.model_dump(), "rail_timetable": timetable}
    return _ok(request, payload)
