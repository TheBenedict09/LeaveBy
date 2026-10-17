import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.adapters.base import USER_AGENT, AdapterResult
from app.core import clock
from app.core.cache import TTLCache
from app.core.resilience import UpstreamError, get_json
from app.core.types import SourceMeta

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


UK_CITIES = [
    GeoPlace("Glasgow, Scotland, United Kingdom", 55.8642, -4.2518),
    GeoPlace("Edinburgh, Scotland, United Kingdom", 55.9533, -3.1883),
    GeoPlace("Paisley, Scotland, United Kingdom", 55.8456, -4.4239),
    GeoPlace("Stirling, Scotland, United Kingdom", 56.1165, -3.9369),
    GeoPlace("Aberdeen, Scotland, United Kingdom", 57.1497, -2.0943),
    GeoPlace("Newcastle upon Tyne, England, United Kingdom", 54.9783, -1.6178),
    GeoPlace("Leeds, England, United Kingdom", 53.8008, -1.5491),
    GeoPlace("Manchester, England, United Kingdom", 53.4808, -2.2426),
    GeoPlace("Birmingham, England, United Kingdom", 52.4862, -1.8904),
    GeoPlace("London, England, United Kingdom", 51.5072, -0.1276),
]


class GeocodeAdapter:
    id = "open-meteo-geocoding"

    def __init__(self, client: httpx.AsyncClient, user_agent: str = USER_AGENT) -> None:
        self._client, self._ua = client, user_agent
        self._cache: TTLCache[list[GeoPlace]] = TTLCache(ttl_s=7 * 24 * 3600)

    async def fetch(self, q: str, limit: int = 5) -> AdapterResult[list[GeoPlace]]:
        key = f"{q.lower()}:{limit}"
        hit = self._cache.get(key)
        if hit:
            return self._result(hit[0], "cached", hit[1], None)
        t0 = time.monotonic()
        try:
            payload = await get_json(
                self._client,
                URL,
                params={"name": q, "count": limit, "language": "en", "countryCode": "GB"},
                headers={"User-Agent": self._ua},
            )
            places = parse_places(payload)
        except UpstreamError:
            needle = q.lower()
            found = [c for c in UK_CITIES if needle in c.label.lower()][:limit]
            meta = SourceMeta(
                id="builtin-uk-cities",
                kind="estimated",
                fetched_at=clock.now(),
                age_s=0,
                licence="Built-in list",
                attribution=None,
            )
            return AdapterResult(data=found, meta=meta)
        self._cache.put(key, places)
        return self._result(places, "live", 0, int((time.monotonic() - t0) * 1000))

    def _result(self, places: list[GeoPlace], kind: str, age_s: float, latency_ms: int | None):
        meta = SourceMeta(
            id=self.id,
            kind=kind,  # type: ignore[arg-type]
            fetched_at=clock.now(),
            age_s=int(age_s),
            latency_ms=latency_ms,
            licence="Non-commercial use",
            attribution="Geocoding by Open-Meteo.com",
        )
        return AdapterResult(data=places, meta=meta)
