"""Everything a request handler needs, built once per app (and replaceable in tests)."""

import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
from fastapi import Request

from app.adapters.base import USER_AGENT
from app.adapters.geocode import GeocodeAdapter
from app.adapters.routing import RoutingAdapter
from app.adapters.tomtom import TrafficAdapter
from app.adapters.weather import WeatherAdapter
from app.core.config import ModelConfig, load_model_config
from app.core.mockdata import MockData, load_mock_data
from app.core.timetable import RailTimetable, load_timetable

if TYPE_CHECKING:
    from app.api.pipeline import Record


class Store:
    """In-memory recommendations, so rescore can reuse a stored simulation. Oldest are dropped."""

    def __init__(self, max_items: int = 200) -> None:
        self._items: OrderedDict[str, Record] = OrderedDict()
        self._max = max_items

    def put(self, rec: "Record") -> None:
        self._items[rec.id] = rec
        self._items.move_to_end(rec.id)
        while len(self._items) > self._max:
            self._items.popitem(last=False)

    def get(self, rec_id: str) -> "Record | None":
        return self._items.get(rec_id)


@dataclass
class Services:
    client: httpx.AsyncClient
    weather: WeatherAdapter
    routing: RoutingAdapter
    geocode: GeocodeAdapter
    cfg: ModelConfig
    data: MockData
    store: Store = field(default_factory=Store)
    timetable: RailTimetable | None = None  # real GB rail timetable extract, if data/rail_timetable.json exists
    traffic: TrafficAdapter | None = None  # TomTom, only when TOMTOM_API_KEY is set

    @classmethod
    def create(
        cls, client: httpx.AsyncClient | None = None, routing_interval_s: float = 1.0, user_agent: str | None = None
    ) -> "Services":
        client = client or httpx.AsyncClient()
        ua = user_agent or os.environ.get("LEAVEBY_USER_AGENT") or USER_AGENT
        return cls(
            client=client,
            weather=WeatherAdapter(client, ua),
            routing=RoutingAdapter(client, ua, min_interval_s=routing_interval_s),
            geocode=GeocodeAdapter(client, ua),
            cfg=load_model_config(),
            data=load_mock_data(),
            timetable=load_timetable(),
            traffic=TrafficAdapter(client, key) if (key := os.environ.get("TOMTOM_API_KEY")) else None,
        )


def get_services(request: Request) -> Services:
    return request.app.state.services
