"""TomTom traffic (car only): travel time with traffic for a given departure, and incidents along the route.

Free tier: routing 20k and incidents 2.5k calls a month, so both are cached. The key is sent as a query
parameter and never appears in errors or logs (resilience.get_json reports the bare URL only)."""

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from app.adapters.base import AdapterResult
from app.core import clock
from app.core.cache import TTLCache
from app.core.resilience import UpstreamError, get_json
from app.core.types import SourceMeta

ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute/{lat1},{lon1}:{lat2},{lon2}/json"
INCIDENTS_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"
INCIDENT_FIELDS = "{incidents{properties{iconCategory,magnitudeOfDelay,delay,events{description},from,to}}}"
ATTRIBUTION = "Traffic by TomTom"
MAX_BBOX_KM2 = 10_000  # TomTom's limit for one incidents request


@dataclass(frozen=True)
class TrafficRoute:
    distance_m: float
    duration_s: float  # with traffic for the requested departure (live or predicted)
    no_traffic_s: float
    basis: Literal["live", "predicted"]
    bbox: tuple[float, float, float, float]  # min lon, min lat, max lon, max lat of the route


@dataclass(frozen=True)
class Incidents:
    count: int
    worst_delay_s: int
    description: str | None


def parse_route(payload: dict[str, Any], basis: Literal["live", "predicted"]) -> TrafficRoute:
    try:
        r = payload["routes"][0]
        s = r["summary"]
        pts = [(p["longitude"], p["latitude"]) for leg in r["legs"] for p in leg["points"]]
        lons, lats = [p[0] for p in pts], [p[1] for p in pts]
        return TrafficRoute(
            float(s["lengthInMeters"]),
            float(s["travelTimeInSeconds"]),
            float(s.get("noTrafficTravelTimeInSeconds", s["travelTimeInSeconds"])),
            basis,
            (min(lons), min(lats), max(lons), max(lats)),
        )
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise UpstreamError(f"tomtom route payload malformed: {e}") from e


def parse_incidents(payload: dict[str, Any]) -> Incidents:
    try:
        props = [i["properties"] for i in payload.get("incidents") or []]
    except (KeyError, TypeError) as e:
        raise UpstreamError(f"tomtom incidents payload malformed: {e}") from e
    delayed = [p for p in props if (p.get("delay") or 0) > 0]
    if not delayed:
        return Incidents(0, 0, None)
    worst = max(delayed, key=lambda p: p["delay"])
    events = worst.get("events") or [{}]
    parts = [events[0].get("description"), worst.get("from") and f"from {worst['from']}"]
    parts.append(worst.get("to") and f"to {worst['to']}")
    text = " ".join(p for p in parts if p) or None
    return Incidents(len(delayed), int(worst["delay"]), text)


def bbox_km2(b: tuple[float, float, float, float]) -> float:
    mid = math.radians((b[1] + b[3]) / 2)
    return (b[2] - b[0]) * 111.32 * math.cos(mid) * (b[3] - b[1]) * 110.57


class TrafficAdapter:
    id = "tomtom"

    def __init__(self, client: httpx.AsyncClient, key: str) -> None:
        self._client, self._key = client, key
        self._routes: TTLCache[TrafficRoute] = TTLCache(ttl_s=15 * 60)
        self._incidents: TTLCache[Incidents] = TTLCache(ttl_s=5 * 60)

    async def route(
        self, origin: tuple[float, float], dest: tuple[float, float], depart_ts: int, live: bool
    ) -> AdapterResult[TrafficRoute]:
        """live: depart now with current traffic; otherwise TomTom's prediction for depart_ts (15 min buckets)."""
        bucket = "now" if live else str(depart_ts // 900)
        key = f"{origin[0]:.3f},{origin[1]:.3f}:{dest[0]:.3f},{dest[1]:.3f}:{bucket}"
        hit = self._routes.get(key)
        if hit:
            return self._result(hit[0], "cached", hit[1], None)
        depart = "now" if live else datetime.fromtimestamp(depart_ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        t0 = time.monotonic()
        payload = await get_json(
            self._client,
            ROUTE_URL.format(lat1=origin[0], lon1=origin[1], lat2=dest[0], lon2=dest[1]),
            params={"key": self._key, "traffic": "true", "departAt": depart, "travelMode": "car"},
        )
        route = parse_route(payload, "live" if live else "predicted")
        self._routes.put(key, route)
        return self._result(route, "live", 0, int((time.monotonic() - t0) * 1000))

    async def incidents(self, bbox: tuple[float, float, float, float]) -> Incidents | None:
        """Incidents happening now inside the route's box; None when the box is too big for one request."""
        if bbox_km2(bbox) > MAX_BBOX_KM2:
            return None
        key = ",".join(f"{v:.2f}" for v in bbox)
        hit = self._incidents.get(key)
        if hit:
            return hit[0]
        payload = await get_json(
            self._client,
            INCIDENTS_URL,
            params={
                "key": self._key,
                "bbox": key,
                "fields": INCIDENT_FIELDS,
                "language": "en-GB",
                "timeValidityFilter": "present",
            },
        )
        found = parse_incidents(payload)
        self._incidents.put(key, found)
        return found

    def _result(self, route: TrafficRoute, kind: str, age_s: float, latency_ms: int | None):
        meta = SourceMeta(
            id=f"tomtom-{route.basis}",
            kind=kind,  # type: ignore[arg-type]
            fetched_at=clock.now(),
            age_s=int(age_s),
            latency_ms=latency_ms,
            licence="TomTom developer terms",
            attribution=ATTRIBUTION,
        )
        return AdapterResult(data=route, meta=meta)
