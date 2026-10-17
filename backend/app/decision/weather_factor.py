"""Weather -> speed factor per mode (blueprint 5.3). All coefficients come from config/model.yaml.
speed_factor is in (0, 1]; duration = base_duration / speed_factor."""

from dataclasses import dataclass

import numpy as np

from app.adapters.weather import WeatherEnsemble
from app.core.config import ModelConfig


@dataclass(frozen=True)
class Conditions:
    """Weather at each (member, departure); every array has shape (M, D). Missing values are made safe."""

    precip: np.ndarray  # mm/h, NaN -> 0
    wind: np.ndarray  # m/s, NaN -> 0
    wind_dir: np.ndarray  # degrees the wind blows FROM; NaN stays NaN (headwind then counts as 0)
    gust: np.ndarray  # m/s, NaN -> 0
    temp: np.ndarray  # deg C, NaN stays NaN (comparison is False, so no ice penalty)
    vis: np.ndarray  # m, NaN -> inf (unlimited)


def nearest_hour_index(times: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Index of the forecast hour closest to each time in t. Shapes: times (H,), t (D,) -> (D,)."""
    return np.abs(times[None, :] - t[:, None]).argmin(axis=1)


def conditions_at(weather: WeatherEnsemble, idx: np.ndarray) -> Conditions:
    def pick(a: np.ndarray) -> np.ndarray:
        return a[:, idx]

    vis = pick(weather.visibility_m)
    return Conditions(
        precip=np.nan_to_num(pick(weather.precip_mm_h), nan=0.0),
        wind=np.nan_to_num(pick(weather.wind_ms), nan=0.0),
        wind_dir=pick(weather.wind_dir_deg),
        gust=np.nan_to_num(pick(weather.gust_ms), nan=0.0),
        temp=pick(weather.temp_c),
        vis=np.where(np.isnan(vis), np.inf, vis),
    )


def headwind_ms(c: Conditions, bearing_deg: float) -> np.ndarray:
    """Component of the wind against the direction of travel. Wind direction is where it blows
    FROM, so wind from straight ahead (same as bearing) is a full headwind; negative = tailwind."""
    hw = c.wind * np.cos(np.radians(c.wind_dir - bearing_deg))
    return np.nan_to_num(hw, nan=0.0)


def speed_factor(mode: str, c: Conditions, bearing_deg: float, cfg: ModelConfig) -> np.ndarray:
    if mode == "bike":
        b = cfg.bike
        f_rain = 1.0 - np.minimum(b.rain_cap, b.k_rain * c.precip)
        over = np.maximum(0.0, headwind_ms(c, bearing_deg) - b.headwind_threshold_ms)
        f_wind = 1.0 - np.minimum(b.headwind_cap, b.k_headwind * over)
        f_cold = np.where(c.temp < b.ice_threshold_c, b.ice_penalty, 1.0)
        f = f_rain * f_wind * f_cold
    elif mode == "drive":
        d = cfg.drive
        f_rain = 1.0 - np.minimum(d.rain_cap, d.k_rain * c.precip)
        f_gust = 1.0 - np.minimum(d.gust_cap, d.k_gust * np.maximum(0.0, c.gust - d.gust_threshold_ms))
        f_vis = np.clip(c.vis / d.visibility_good_m, d.visibility_floor, 1.0)
        f = f_rain * f_gust * f_vis
    elif mode == "walk":
        w = cfg.walk
        f = 1.0 - np.minimum(w.rain_cap, w.k_rain * c.precip)
    else:
        raise ValueError(f"no weather model for mode {mode!r}")
    return np.clip(f, cfg.speed.min_factor, 1.0)
