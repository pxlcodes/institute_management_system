"""Small in-process caches for frequently used reference data.

The desktop application is deliberately a single-process application.  A tiny
time-bound cache is therefore enough for the lookup lists used by forms, while
keeping records current after every save.
"""

from __future__ import annotations

from time import monotonic
from typing import Callable, TypeVar


T = TypeVar("T")


class LookupCache:
    """Cache read-only lookup rows briefly, with explicit invalidation."""

    def __init__(self, ttl_seconds: float = 20.0):
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._entries: dict[str, tuple[float, object]] = {}

    def get(self, key: str, loader: Callable[[], T]) -> T:
        entry = self._entries.get(key)
        now = monotonic()
        if entry is not None and entry[0] > now:
            return entry[1]  # type: ignore[return-value]
        value = loader()
        self._entries[key] = (now + self.ttl_seconds, value)
        return value

    def clear(self) -> None:
        self._entries.clear()
