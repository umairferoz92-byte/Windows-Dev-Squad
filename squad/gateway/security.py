"""Gateway security helpers: rate limiting and output escaping."""

from __future__ import annotations

import html
import time


def escape_html(value: str) -> str:
    return html.escape(value or "", quote=True)


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, clock=time.time):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        bucket = [t for t in self._hits.get(key, []) if now - t < self.window]
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        self._hits[key] = bucket
        return True
