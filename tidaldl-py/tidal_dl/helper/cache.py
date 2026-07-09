"""Thread-safe TTL cache for TIDAL API responses."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any


class TTLCache:
    """In-memory cache with per-entry expiry."""

    def __init__(self, ttl_sec: int = 300) -> None:
        self._ttl = ttl_sec
        self._entries: dict[str, tuple[Any, float]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            value, ts = entry
            if time.monotonic() - ts > self._ttl:
                del self._entries[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._entries[key] = (value, time.monotonic())

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)