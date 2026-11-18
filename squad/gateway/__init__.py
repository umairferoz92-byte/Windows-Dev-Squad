"""Remote web gateway (Phase 10). Bound to 127.0.0.1 only."""

from __future__ import annotations

from squad.gateway.app import ALLOWED_HOSTS, APPROVABLE_ACTIONS, create_app
from squad.gateway.auth import DEFAULT_TTL_SECONDS, SessionStore
from squad.gateway.controller import RemoteController

__all__ = [
    "create_app",
    "SessionStore",
    "RemoteController",
    "ALLOWED_HOSTS",
    "APPROVABLE_ACTIONS",
    "DEFAULT_TTL_SECONDS",
]
