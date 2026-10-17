"""Shared builders for tests that need weather without the network."""

import numpy as np

from app.adapters.weather import WeatherEnsemble

T0 = 1_792_000_000
H = 120
DEADLINE = T0 + 30 * 3600


def weather(
    precip=0.0, wind=0.0, wind_dir=0.0, gust=0.0, temp=10.0, vis=24000.0, members=6, hours=H
) -> WeatherEnsemble:
    def full(v):
        return np.full((members, hours), float(v))

    return WeatherEnsemble(
        lat=55.86,
        lon=-4.26,
        times=T0 + 3600 * np.arange(hours, dtype=np.int64),
        precip_mm_h=full(precip),
        wind_ms=full(wind),
        wind_dir_deg=full(wind_dir),
        gust_ms=full(gust),
        temp_c=full(temp),
        visibility_m=full(vis),
    )
