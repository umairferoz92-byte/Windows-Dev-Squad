"""Short-lived web session tokens."""

from __future__ import annotations

import secrets
import time

DEFAULT_TTL_SECONDS = 900  # 15 minutes


class SessionStore:
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, clock=time.time):
        self._sessions: dict[str, float] = {}
        self._ttl = ttl_seconds
        self._clock = clock

    def issue(self) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = self._clock()
        return token

    def valid(self, token: str) -> bool:
        created = self._sessions.get(token)
        if created is None:
            return False
        if self._clock() - created > self._ttl:
            self._sessions.pop(token, None)
            return False
        return True

    def revoke_all(self) -> None:
        self._sessions.clear()

    def count(self) -> int:
        return len(self._sessions)
