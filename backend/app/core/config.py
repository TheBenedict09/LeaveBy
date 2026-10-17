"""Model configuration loaded from config/model.yaml (blueprint 5.3, 5.4)."""

import os
from datetime import time
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GridCfg(_Cfg):
    step_min: int
    earliest_mult: float
    latest_mult: float
    pad_min: int


class NoiseCfg(_Cfg):
    n_draws: int
    sigma: dict[str, float]


class SpeedCfg(_Cfg):
    min_factor: float


class BikeCfg(_Cfg):
    k_rain: float
    rain_cap: float
    k_headwind: float
    headwind_threshold_ms: float
    headwind_cap: float
    ice_threshold_c: float
    ice_penalty: float


class DriveCfg(_Cfg):
    k_rain: float
    rain_cap: float
    gust_threshold_ms: float
    k_gust: float
    gust_cap: float
    visibility_good_m: float
    visibility_floor: float


class WalkCfg(_Cfg):
    k_rain: float
    rain_cap: float


class RailCfg(_Cfg):
    station_radius_m: float
    headway_min: int
    speed_table_km_kmh: list[tuple[float, float]]
    timezone: str
    first_departure: time
    last_departure: time
    access_min: float
    egress_min: float
    calm_within_5min_target: float
    calm_target_sources: list[str]
    p_on_time_base: float
    delay_median_min: float
    delay_sigma: float
    delay_cap_min: float
    gust_threshold_ms: float
    k_gust: float
    max_delay_prob: float


class ModelConfig(_Cfg):
    status: str
    grid: GridCfg
    noise: NoiseCfg
    speed: SpeedCfg
    bike: BikeCfg
    drive: DriveCfg
    walk: WalkCfg
    rail: RailCfg


DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "model.yaml"


@lru_cache
def load_model_config(path: str | None = None) -> ModelConfig:
    """Cached and shared: tests that tweak values must use cfg.model_copy(deep=True)."""
    p = Path(path or os.environ.get("LEAVEBY_MODEL_CONFIG") or DEFAULT_PATH)
    return ModelConfig.model_validate(yaml.safe_load(p.read_text()))
