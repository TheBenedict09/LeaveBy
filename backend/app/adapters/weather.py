"""Open-Meteo ensemble adapter. Returns a normalised WeatherEnsemble (SI units, arrays shaped
(members, hours)); the decision layer never sees provider JSON."""

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np

from app.adapters.base import USER_AGENT, AdapterResult
from app.core import clock
from app.core.cache import TTLCache
from app.core.resilience import UpstreamError, get_json
from app.core.types import SourceMeta

URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
VARIABLES = {
    "precipitation": "precip_mm_h",
    "wind_speed_10m": "wind_ms",
    "wind_direction_10m": "wind_dir_deg",
    "wind_gusts_10m": "gust_ms",
    "temperature_2m": "temp_c",
    "visibility": "visibility_m",
}
STALE_LIMIT_S = 6 * 3600


@dataclass(frozen=True)
class WeatherEnsemble:
    lat: float
    lon: float
    times: np.ndarray  # int64 unix seconds (UTC), shape (hours,)
    precip_mm_h: np.ndarray  # each of these: float, shape (members, hours); NaN = missing
    wind_ms: np.ndarray
    wind_dir_deg: np.ndarray
    gust_ms: np.ndarray
    temp_c: np.ndarray
    visibility_m: np.ndarray

    @property
    def n_members(self) -> int:
        return self.precip_mm_h.shape[0]


def _member_rows(hourly: dict[str, Any], var: str, n_hours: int) -> np.ndarray:
    """Collect `var` (control) and `var_memberNN` series into a (members, hours) array."""
    pat = re.compile(rf"^{re.escape(var)}(_member\d+)?$")
    keys = sorted(k for k in hourly if pat.match(k))
    rows = []
    for k in keys:
        series = hourly[k]
        if not isinstance(series, list) or len(series) != n_hours:
            raise UpstreamError(f"weather series {k} has unexpected shape")
        rows.append([np.nan if v is None else float(v) for v in series])
    return np.array(rows, dtype=float).reshape(len(rows), n_hours)


def _parse_times(raw: list[Any], utc_offset_s: int) -> np.ndarray:
    if raw and isinstance(raw[0], int | float):  # timeformat=unixtime
        return np.array(raw, dtype=np.int64)
    out = []  # ISO strings in the requested timezone, e.g. "2026-10-17T12:00"
    for s in raw:
        local = datetime.fromisoformat(s).replace(tzinfo=UTC)
        out.append(int(local.timestamp()) - utc_offset_s)
    return np.array(out, dtype=np.int64)


def parse_ensemble(payload: dict[str, Any]) -> WeatherEnsemble:
    try:
        hourly = payload["hourly"]
        times = _parse_times(hourly["time"], int(payload.get("utc_offset_seconds", 0)))
        n = len(times)
        arrays = {attr: _member_rows(hourly, var, n) for var, attr in VARIABLES.items()}
        if arrays["precip_mm_h"].shape[0] == 0:
            raise UpstreamError("weather payload has no precipitation members")
        members = arrays["precip_mm_h"].shape[0]
        for attr, a in arrays.items():
            if a.shape[0] == 0:  # variable missing entirely (e.g. visibility): treat as unknown
                arrays[attr] = np.full((members, n), np.nan)
            elif a.shape[0] != members:
                raise UpstreamError(f"weather variable {attr} has {a.shape[0]} members, expected {members}")
        return WeatherEnsemble(float(payload["latitude"]), float(payload["longitude"]), times, **arrays)
    except (KeyError, TypeError, ValueError) as e:
        raise UpstreamError(f"weather payload malformed: {e}") from e


class WeatherAdapter:
    id = "open-meteo-ensemble"

    def __init__(self, client: httpx.AsyncClient, user_agent: str = USER_AGENT) -> None:
        self._client = client
        self._ua = user_agent
        self._cache: TTLCache[WeatherEnsemble] = TTLCache(ttl_s=1800)

    async def fetch(self, lat: float, lon: float, days: int = 7) -> AdapterResult[WeatherEnsemble]:
        key = f"{lat:.2f},{lon:.2f},{days}"
        fresh = self._cache.get(key)
        if fresh:
            return self._result(fresh[0], "cached", fresh[1], None)
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(VARIABLES),
            "models": "ecmwf_ifs025",
            "forecast_days": days,
            "wind_speed_unit": "ms",
            "timeformat": "unixtime",
        }
        t0 = time.monotonic()
        try:
            payload = await get_json(self._client, URL, params=params, headers={"User-Agent": self._ua})
            data = parse_ensemble(payload)
        except UpstreamError:
            stale = self._cache.get(key, max_age_s=STALE_LIMIT_S)
            if stale:
                return self._result(stale[0], "cached", stale[1], None)
            raise
        self._cache.put(key, data)
        return self._result(data, "live", 0, int((time.monotonic() - t0) * 1000))

    def _result(self, data: WeatherEnsemble, kind: str, age_s: float, latency_ms: int | None):
        meta = SourceMeta(
            id=self.id,
            kind=kind,  # type: ignore[arg-type]
            fetched_at=clock.now(),
            age_s=int(age_s),
            latency_ms=latency_ms,
            licence="Non-commercial use",
            attribution="Weather data by Open-Meteo.com",
        )
        return AdapterResult(data=data, meta=meta)
