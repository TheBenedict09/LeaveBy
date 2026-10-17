from collections.abc import Callable
from time import monotonic
from typing import Generic, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    """In-memory cache that remembers the last good value, so callers can choose between
    'fresh' (age <= ttl) and 'stale but usable' (age <= max_stale) results."""

    def __init__(self, ttl_s: float, clock: Callable[[], float] = monotonic) -> None:
        self.ttl_s = ttl_s
        self._clock = clock
        self._items: dict[str, tuple[float, V]] = {}

    def put(self, key: str, value: V) -> None:
        self._items[key] = (self._clock(), value)

    def get(self, key: str, max_age_s: float | None = None) -> tuple[V, float] | None:
        """Return (value, age_s) if present and not older than max_age_s (default: the ttl)."""
        item = self._items.get(key)
        if item is None:
            return None
        age = self._clock() - item[0]
        if age > (self.ttl_s if max_age_s is None else max_age_s):
            return None
        return item[1], age
