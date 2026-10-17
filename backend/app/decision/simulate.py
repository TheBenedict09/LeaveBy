"""Monte Carlo journey-time simulation (blueprint 5.2 step 5, 5.9, 5.10).

One scenario = one forecast ensemble member x one traffic-noise draw. The noise field is built once
per request and shared by every mode (common random numbers), which is what later makes
'pin a morning' and the hedge meaningful."""

from dataclasses import dataclass

import numpy as np

from app.adapters.weather import WeatherEnsemble
from app.core.config import ModelConfig
from app.decision.weather_factor import conditions_at, nearest_hour_index, speed_factor


@dataclass(frozen=True)
class SimResult:
    mode: str
    departures: np.ndarray  # (D,) int64 unix seconds
    durations: np.ndarray  # (D, M, K) seconds

    @property
    def arrivals(self) -> np.ndarray:  # (D, M, K) unix seconds
        return self.departures[:, None, None] + self.durations


def make_noise(seed: int, n_members: int, n_draws: int) -> np.ndarray:
    """Standard-normal field (M, K), deterministic in the seed and shared across modes."""
    return np.random.default_rng(seed).standard_normal((n_members, n_draws))


def departure_grid(deadline_ts: int, base_duration_s: float, cfg: ModelConfig) -> np.ndarray:
    g = cfg.grid
    step = g.step_min * 60
    earliest = deadline_ts - base_duration_s * g.earliest_mult - g.pad_min * 60
    latest = deadline_ts - base_duration_s * g.latest_mult
    start = int(np.floor(earliest / step)) * step
    stop = int(np.floor(latest / step)) * step
    return np.arange(start, stop + step, step, dtype=np.int64)


def simulate(
    mode: str,
    base_duration_s: float,
    bearing_deg: float,
    weather: WeatherEnsemble,
    departures: np.ndarray,
    noise_z: np.ndarray,
    cfg: ModelConfig,
) -> SimResult:
    if noise_z.shape[0] != weather.n_members:
        raise ValueError("noise field and weather ensemble must have the same number of members")
    t_mid = departures + base_duration_s / 2.0  # sample the weather half way through the trip
    idx = nearest_hour_index(weather.times, t_mid)
    wf = speed_factor(mode, conditions_at(weather, idx), bearing_deg, cfg)  # (M, D)
    eps = np.exp(cfg.noise.sigma[mode] * noise_z)  # (M, K), median 1
    durations = base_duration_s / wf.T[:, :, None] * eps[None, :, :]  # (D, M, K)
    return SimResult(mode, departures, durations)
