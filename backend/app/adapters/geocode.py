from dataclasses import dataclass
from typing import Any

from app.core.resilience import UpstreamError

URL = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass(frozen=True)
class GeoPlace:
    label: str
    lat: float
    lon: float


def parse_places(payload: dict[str, Any]) -> list[GeoPlace]:
    """Missing 'results' means no match (not an error). Malformed entries are skipped."""
    out: list[GeoPlace] = []
    try:
        for r in payload.get("results") or []:
            try:
                parts = [r["name"], r.get("admin1"), r.get("country")]
                out.append(GeoPlace(", ".join(p for p in parts if p), float(r["latitude"]), float(r["longitude"])))
            except (KeyError, TypeError, ValueError):
                continue
    except AttributeError as e:
        raise UpstreamError("geocode payload malformed") from e
    return out
