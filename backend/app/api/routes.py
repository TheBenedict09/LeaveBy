from datetime import timedelta

from fastapi import APIRouter, Request

from app.api import envelope
from app.api.schemas import (
    Envelope,
    Headline,
    RecommendationData,
    RecommendationRequest,
)

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/recommendations", response_model=Envelope[RecommendationData], tags=["recommendations"])
def create_recommendation(body: RecommendationRequest, request: Request) -> dict:
    """STUB (step 3): returns a fixed headline. The real engine replaces this body in step 6."""
    leave_at = body.arrive_by - timedelta(minutes=78)
    data = RecommendationData(
        recommendation_id="rec_stub_0001",
        headline=Headline(mode="train", leave_at=leave_at, p_on_time=0.96, on_time_scenarios=49, total_scenarios=51),
    )
    return {"ok": True, "data": data.model_dump(mode="json"), "meta": envelope.meta(request.state.request_id)}
