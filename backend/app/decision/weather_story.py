"""The forecast for the trip in plain terms, and what it costs in minutes. Reads the same ensemble the simulation
used, and the same coefficients (config/model.yaml), so every sentence is derived, never invented."""

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import numpy as np

from app.adapters.weather import WeatherEnsemble
from app.core.config import ModelConfig
from app.decision.engine import Decision
from app.decision.weather_factor import conditions_at, nearest_hour_index

RAIN_MM_H = 0.5  # a forecast member counts as "rain" from light rain upwards
MS_TO_MPH = 2.23694

SUBJECT = {"walk": "Walking", "bike": "Cycling", "drive": "Driving", "train": "The train"}


@dataclass(frozen=True)
class WeatherPoint:
    """The ensemble at one time, near the start of the trip."""

    at: int
    members: int
    members_with_rain: int
    rain_mm_h_median: float
    rain_mm_h_p90: float  # the wet end of the forecast
    gust_mph_median: float
    gust_mph_p90: float
    temp_c_median: float | None
    visibility_m_median: float | None


def dry_weather(w: WeatherEnsemble) -> WeatherEnsemble:
    """The same ensemble with no rain, wind or fog, so a re-run with the same seed isolates the weather's effect."""
    zero = np.zeros_like(w.precip_mm_h)
    return replace(
        w,
        precip_mm_h=zero,
        wind_ms=zero,
        gust_ms=zero,
        temp_c=np.full_like(w.temp_c, 10.0),
        visibility_m=np.full_like(w.visibility_m, 1e5),
    )


def stormy(w: WeatherEnsemble, cfg: ModelConfig) -> WeatherEnsemble:
    """DEMO ONLY: the same ensemble made stormy by fixed amounts (config storm_demo). Never the real forecast."""
    s = cfg.storm_demo
    return replace(
        w,
        precip_mm_h=np.nan_to_num(w.precip_mm_h) + s.rain_add_mm_h,
        wind_ms=np.nan_to_num(w.wind_ms) + s.wind_add_ms,
        gust_ms=np.nan_to_num(w.gust_ms) + s.gust_add_ms,
        visibility_m=np.fmin(np.nan_to_num(w.visibility_m, nan=np.inf), s.visibility_cap_m),
    )


def point(w: WeatherEnsemble, ts: int) -> WeatherPoint:
    c = conditions_at(w, nearest_hour_index(w.times, np.array([ts])))
    rain, gust = c.precip[:, 0], c.gust[:, 0] * MS_TO_MPH

    def med(a: np.ndarray) -> float | None:
        a = a[np.isfinite(a)]
        return float(np.median(a)) if a.size else None

    return WeatherPoint(
        at=ts,
        members=int(rain.size),
        members_with_rain=int((rain >= RAIN_MM_H).sum()),
        rain_mm_h_median=float(np.median(rain)),
        rain_mm_h_p90=float(np.quantile(rain, 0.9)),
        gust_mph_median=float(np.median(gust)),
        gust_mph_p90=float(np.quantile(gust, 0.9)),
        temp_c_median=med(c.temp[:, 0]),
        visibility_m_median=med(c.vis[:, 0]),
    )


def members_at(w: WeatherEnsemble, ts: int) -> list[tuple[float, float]]:
    """(rain mm/h, gust mph) for every forecast member at one time, in member order (as the raincloud dots)."""
    c = conditions_at(w, nearest_hour_index(w.times, np.array([ts])))
    return [(float(r), float(g * MS_TO_MPH)) for r, g in zip(c.precip[:, 0], c.gust[:, 0], strict=True)]


def train_late_risk(w: WeatherEnsemble, ts: int, cfg: ModelConfig) -> tuple[float, float]:
    """(calm, forecast) chance that a train runs more than 5 min late, from the delay model's own parameters."""
    r = cfg.rail
    # P(a delayed train is more than 5 min late), from the lognormal delay length
    over_5 = 0.5 * math.erfc(math.log(5 / r.delay_median_min) / (r.delay_sigma * math.sqrt(2)))
    gust = conditions_at(w, nearest_hour_index(w.times, np.array([ts]))).gust[:, 0]
    p = np.clip((1 - r.p_on_time_base) + r.k_gust * np.maximum(0.0, gust - r.gust_threshold_ms), 0, r.max_delay_prob)
    return (1 - r.p_on_time_base) * over_5, float(p.mean()) * over_5


def extra_minutes(actual: Decision, dry: Decision) -> dict[str, float]:
    """How much earlier the weather makes you leave, per option feasible in both."""
    leave = {o.mode: o.summary.leave_by_ts for o in dry.options if o.feasible and o.summary.leave_by_ts}
    return {
        o.mode: (leave[o.mode] - o.summary.leave_by_ts) / 60
        for o in actual.options
        if o.feasible and o.summary.leave_by_ts and o.mode in leave
    }


def tips(
    w: WeatherEnsemble, dep: WeatherPoint, start: int, end: int, extra: dict[str, float], d: Decision, cfg: ModelConfig
) -> list[str]:
    """Advice that follows from the forecast. Each line is only added when the data says it is true."""
    out: list[str] = []
    if dep.members_with_rain * 2 > dep.members:
        out.append(
            f"Rain is likely when you set off ({dep.members_with_rain} of {dep.members} forecasts): take a waterproof."
        )
    hours = np.arange((start // 3600) * 3600, end + 1, 3600)
    if hours.size:
        rain = conditions_at(w, nearest_hour_index(w.times, hours)).precip
        share = (rain >= RAIN_MM_H).mean(axis=0)
        peak = int(np.argmax(share))
        if share[peak] > 0.5 and share[peak] > share[0]:
            n = int((rain[:, peak] >= RAIN_MM_H).sum())
            at = datetime.fromtimestamp(int(hours[peak]), UTC).astimezone(ZoneInfo(cfg.rail.timezone)).strftime("%H:%M")
            out.append(f"Rain is most likely around {at} ({n} of {rain.shape[0]} forecasts).")
    if dep.gust_mph_median >= cfg.drive.gust_threshold_ms * MS_TO_MPH:
        out.append(f"Gusts around {dep.gust_mph_median:.0f} mph: cycling will be slow and exposed.")
    if dep.temp_c_median is not None and dep.temp_c_median < cfg.bike.ice_threshold_c:
        out.append("Near freezing when you leave: watch for ice if cycling or walking.")
    win = d.winner
    if win is not None and win.mode in extra and len(extra) > 1:
        worse = {m: v for m, v in extra.items() if m != win.mode and v - extra[win.mode] >= 1}
        if worse and all(v >= extra[win.mode] for v in extra.values()):
            # e.g. "The train copes best with this weather: driving needs 6 min more."
            base = extra[win.mode]
            others = ", ".join(f"{SUBJECT[m].lower()} needs {v - base:.0f} min more" for m, v in worse.items())
            out.append(f"{SUBJECT[win.mode]} copes best with this weather: {others}.")
    return out
