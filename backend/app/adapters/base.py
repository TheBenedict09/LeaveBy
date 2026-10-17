from dataclasses import dataclass
from typing import Generic, TypeVar

from app.core.types import SourceMeta

Res = TypeVar("Res")

USER_AGENT = "LeaveBy-hackathon/0.1 (contact: set LEAVEBY_USER_AGENT)"


@dataclass(frozen=True)
class AdapterResult(Generic[Res]):
    data: Res
    meta: SourceMeta
