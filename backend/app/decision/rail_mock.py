"""MOCK rail model (blueprint 5.4). A generated timetable with a fixed headway; each scenario is either
a normal run or a delayed one. Gusts above a threshold make delays more likely. Everything here is
simulated and must be labelled mock wherever it is shown.

The returned SimResult is keyed by the time the user LEAVES HOME, so leave-by logic is the same as for
every other mode; the 'cliff' is stepped because missing a train costs a whole headway."""

import numpy as np

from app.adapters.weather import WeatherEnsemble
from app.core.config import ModelConfig
from app.decision.simulate import SimResult
from app.decision.weather_factor import conditions_at, nearest_hour_index


def rail_times(distance_m: float, cfg: ModelConfig) -> tuple[float, float, float]:
    """(access_s, ride_s, egress_s)."""
    r = cfg.rail
    return r.access_min * 60.0, distance_m / 1000.0 / r.avg_speed_kmh * 3600.0, r.egress_min * 60.0


def train_departures(deadline_ts: int, distance_m: float, cfg: ModelConfig) -> np.ndarray:
    """Scheduled train departures (unix s), from 'certainly on time' to 'hopelessly late'."""
    access_s, ride_s, egress_s = rail_times(distance_m, cfg)
    step = cfg.rail.headway_min * 60
    earliest = deadline_ts - (access_s + ride_s + egress_s) * cfg.grid.earliest_mult - cfg.grid.pad_min * 60
    latest = deadline_ts - (ride_s + egress_s) * cfg.grid.latest_mult
    start = int(np.floor(earliest / step)) * step
    stop = int(np.floor(latest / step)) * step
    return np.arange(start, stop + step, step, dtype=np.int64)


def make_rail_noise(seed: int, n_members: int, n_draws: int) -> tuple[np.ndarray, np.ndarray]:
    """(u, z), both (M, K): uniform for 'is it delayed', normal for 'how long'. Deterministic in the seed."""
    rng = np.random.default_rng([seed, 1])
    return rng.random((n_members, n_draws)), rng.standard_normal((n_members, n_draws))


def simulate_train(
    distance_m: float,
    weather: WeatherEnsemble,
    train_deps: np.ndarray,
    rail_noise: tuple[np.ndarray, np.ndarray],
    cfg: ModelConfig,
) -> SimResult:
    r = cfg.rail
    access_s, ride_s, egress_s = rail_times(distance_m, cfg)
    u, z = rail_noise
    if u.shape[0] != weather.n_members:
        raise ValueError("rail noise and weather ensemble must have the same number of members")
    idx = nearest_hour_index(weather.times, train_deps + ride_s / 2.0)
    gust = conditions_at(weather, idx).gust  # (M, D)
    p_delay = np.clip(
        (1.0 - r.p_on_time_base) + r.k_gust * np.maximum(0.0, gust - r.gust_threshold_ms), 0.0, r.max_delay_prob
    )
    delayed = u[None, :, :] < p_delay.T[:, :, None]  # (D, M, K)
    delay_s = np.minimum(r.delay_median_min * 60.0 * np.exp(r.delay_sigma * z), r.delay_cap_min * 60.0)  # (M, K)
    durations = access_s + ride_s + egress_s + np.where(delayed, delay_s[None, :, :], 0.0)
    leave_home = train_deps - int(round(access_s))
    return SimResult("train", leave_home.astype(np.int64), durations)
