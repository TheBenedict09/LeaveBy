"""Degraded-mode stand-ins (blueprint section 9). Everything built here is flagged 'estimated' by the caller."""

import math

import numpy as np

from app.adapters.routing import Route, bearing
from app.adapters.weather import WeatherEnsemble

DETOUR = 1.3  # road distance is longer than the straight line
SPEED_MS = {"car": 60 / 3.6, "bike": 15 / 3.6, "foot": 5 / 3.6}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(a))


def estimate_route(profile: str, origin: tuple[float, float], dest: tuple[float, float]) -> Route:
    """origin / dest are (lat, lon). Straight line times a detour factor at a typical speed."""
    dist = haversine_m(origin[0], origin[1], dest[0], dest[1]) * DETOUR
    brg = bearing(origin[1], origin[0], dest[1], dest[0])
    return Route(profile, dist, dist / SPEED_MS[profile], brg, [(origin[1], origin[0]), (dest[1], dest[0])])


def neutral_weather(deadline_ts: int, members: int = 51, hours: int = 240) -> WeatherEnsemble:
    """Calm, dry 'no weather risk' ensemble used when the forecast is unavailable."""
    start = (deadline_ts // 3600) * 3600 - (hours // 2) * 3600

    def full(v: float) -> np.ndarray:
        return np.full((members, hours), v)

    return WeatherEnsemble(
        lat=0.0,
        lon=0.0,
        times=start + 3600 * np.arange(hours, dtype=np.int64),
        precip_mm_h=full(0.0),
        wind_ms=full(0.0),
        wind_dir_deg=full(0.0),
        gust_ms=full(0.0),
        temp_c=full(10.0),
        visibility_m=full(24000.0),
    )
