"""Types shared by every layer (adapters produce them, the API publishes them)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal["live", "static", "mock", "cached", "estimated", "recorded"]  # static: a real published file


class SourceMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SourceKind
    fetched_at: datetime
    age_s: int = Field(ge=0)
    latency_ms: int | None = None
    licence: str
    attribution: str | None = None
