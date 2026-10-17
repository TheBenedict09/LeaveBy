"""Public API contract (blueprint section 8). Pydantic models are the source of truth;
openapi.yaml is exported from them and a contract test fails if the two drift."""

from datetime import datetime, timedelta
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core import clock
from app.core.types import SourceMeta

Mode = Literal["walk", "bike", "drive", "train"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # reject unknown fields (section 8.7)


class Place(Strict):
    label: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Weights(Strict):
    time: float = Field(0.4, ge=0, le=1)
    cost: float = Field(0.2, ge=0, le=1)
    carbon: float = Field(0.2, ge=0, le=1)
    accessibility: float = Field(0.2, ge=0, le=1)

    @model_validator(mode="after")
    def _some_positive(self) -> "Weights":
        if self.time + self.cost + self.carbon + self.accessibility <= 0:
            raise ValueError("at least one weight must be greater than 0")
        return self

    def normalised(self) -> "Weights":
        s = self.time + self.cost + self.carbon + self.accessibility
        return Weights(
            time=self.time / s,
            cost=self.cost / s,
            carbon=self.carbon / s,
            accessibility=self.accessibility / s,
        )


class Constraints(Strict):
    step_free: bool = False
    max_walk_m: int = Field(1200, ge=0, le=20000)
    has_luggage: bool = False
    has_car: bool = False


class Options(Strict):
    stress_test: bool = False
    hedge: bool = True
    explain: Literal["template", "llm"] = "template"


class RecommendationRequest(Strict):
    origin: Place
    destination: Place
    arrive_by: datetime
    confidence: float = Field(0.95, ge=0.5, le=0.99)
    weights: Weights = Weights()
    constraints: Constraints = Constraints()
    options: Options = Options()

    @field_validator("arrive_by")
    @classmethod
    def _within_next_7_days(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("must include a UTC offset")
        now = clock.now()
        if not (now < v <= now + timedelta(days=7)):
            raise ValueError("must be within the next 7 days")
        return v


class Warning(Strict):
    code: str
    message: str


class Meta(Strict):
    request_id: str
    generated_at: datetime
    seed: int | None = None
    degraded: bool = False
    warnings: list[Warning] = []
    sources: list[SourceMeta] = []


class FieldError(Strict):
    path: str
    message: str


class ErrorBody(Strict):
    type: str
    title: str
    status: int
    code: Literal["VALIDATION_ERROR", "NOT_FOUND", "RATE_LIMITED", "UPSTREAM_UNAVAILABLE", "INTERNAL"]
    detail: str
    fields: list[FieldError] = []


class RescoreRequest(Strict):
    """Any field left out keeps the value from the original request."""

    confidence: float | None = Field(None, ge=0.5, le=0.99)
    weights: Weights | None = None
    constraints: Constraints | None = None
    options: Options | None = None


class Headline(Strict):
    mode: Mode
    leave_at: datetime
    p_on_time: float = Field(ge=0, le=1)
    on_time_scenarios: int = Field(ge=0)
    total_scenarios: int = Field(ge=1)


class ArrivalQuantiles(Strict):
    p05: datetime
    p50: datetime
    p95: datetime


class CliffPoint(Strict):
    leave: datetime
    p_on_time: float = Field(ge=0, le=1)


class AccessibilityOut(Strict):
    feasible: bool
    score: float = Field(ge=0, le=1)


class OptionOut(Strict):
    mode: Mode
    rank: int | None
    score: float | None
    feasible: bool
    infeasible_reason: str | None
    leave_by: datetime | None
    p_on_time: float = Field(ge=0, le=1)
    on_time_scenarios: int = Field(ge=0)
    total_scenarios: int = Field(ge=1)
    arrival: ArrivalQuantiles
    journey_at_risk_min: float
    cost_gbp: float
    co2e_kg: float
    accessibility: AccessibilityOut
    cliff: list[CliffPoint]
    scenario_arrivals: list[datetime]
    provenance: list[str]


class HedgeOut(Strict):
    backup_mode: Mode
    leave_at: datetime
    p_both_late: float = Field(ge=0, le=1)
    both_late_scenarios: int = Field(ge=0)
    total_scenarios: int = Field(ge=1)
    reason: str | None


class ExplanationOut(Strict):
    mode: Literal["template"] = "template"
    because: list[str]
    tradeoffs: list[str]
    flip_points: list[str]


class RecommendationData(Strict):
    recommendation_id: str
    headline: Headline | None  # None when no option can reach the confidence level
    options: list[OptionOut]
    hedge: HedgeOut | None
    explanation: ExplanationOut
    assumptions_ref: str = "/v1/assumptions"


class GeocodeData(Strict):
    places: list[Place]


class SourceInfo(Strict):
    id: str
    kind: Literal["live", "mock", "cached", "estimated"]
    role: str
    licence: str
    attribution: str | None = None


class SourcesData(Strict):
    sources: list[SourceInfo]


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: ErrorBody | None = None
    meta: Meta
