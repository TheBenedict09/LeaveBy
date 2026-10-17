"""FOSSGIS OSRM adapter (car / bike / foot). Policy: max 1 request per second, honest User-Agent."""

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.adapters.base import USER_AGENT, AdapterResult
from app.core import clock
from app.core.cache import TTLCache
from app.core.resilience import UpstreamError, get_json
from app.core.types import SourceMeta

Profile = Literal["car", "bike", "foot"]
BASE = "https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"


@dataclass(frozen=True)
class Route:
    profile: str
    distance_m: float
    duration_s: float
    bearing_deg: float  # initial bearing origin -> destination, 0 = north, clockwise
    geometry: list[tuple[float, float]]  # (lon, lat)


def bearing(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def parse_route(profile: str, payload: dict[str, Any]) -> Route:
    try:
        if payload.get("code") != "Ok":
            raise UpstreamError(f"routing returned code {payload.get('code')!r}")
        r = payload["routes"][0]
        coords = [(float(x), float(y)) for x, y in r["geometry"]["coordinates"]]
        (lon1, lat1), (lon2, lat2) = coords[0], coords[-1]
        return Route(profile, float(r["distance"]), float(r["duration"]), bearing(lon1, lat1, lon2, lat2), coords)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise UpstreamError(f"routing payload malformed: {e}") from e


class RoutingAdapter:
    id = "osrm"

    def __init__(self, client: httpx.AsyncClient, user_agent: str = USER_AGENT, min_interval_s: float = 1.0) -> None:
        self._client, self._ua = client, user_agent
        self._min_interval_s = min_interval_s
        self._cache: TTLCache[Route] = TTLCache(ttl_s=24 * 3600)
        self._last_call = 0.0

    async def _throttle(self) -> None:
        wait = self._min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()

    async def fetch(self, profile: Profile, origin: tuple[float, float], dest: tuple[float, float]):
        """origin / dest are (lat, lon)."""
        key = f"{profile}:{origin[0]:.4f},{origin[1]:.4f}:{dest[0]:.4f},{dest[1]:.4f}"
        hit = self._cache.get(key)
        if hit:
            return self._result(hit[0], "cached", hit[1], None)
        url = BASE.format(profile=profile, lat1=origin[0], lon1=origin[1], lat2=dest[0], lon2=dest[1])
        await self._throttle()
        t0 = time.monotonic()
        payload = await get_json(
            self._client,
            url,
            params={"overview": "simplified", "geometries": "geojson"},
            headers={"User-Agent": self._ua},
        )
        route = parse_route(profile, payload)
        self._cache.put(key, route)
        return self._result(route, "live", 0, int((time.monotonic() - t0) * 1000))

    def _result(self, route: Route, kind: str, age_s: float, latency_ms: int | None):
        meta = SourceMeta(
            id=self.id,
            kind=kind,  # type: ignore[arg-type]
            fetched_at=clock.now(),
            age_s=int(age_s),
            latency_ms=latency_ms,
            licence="ODbL (OpenStreetMap contributors)",
            attribution="Routing by FOSSGIS OSRM; map data (c) OpenStreetMap contributors",
        )
        return AdapterResult(data=route, meta=meta)
