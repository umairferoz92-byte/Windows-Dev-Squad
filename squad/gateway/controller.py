"""The object the gateway talks to. Budgets can only be lowered, never raised."""

from __future__ import annotations

import time


class RemoteController:
    def __init__(
        self,
        budget_caps: dict | None = None,
        idle_timeout_seconds: float = 900,
        clock=time.time,
        live_state: dict | None = None,
    ):
        """A controller that can be linked to a live squad run.

        ``live_state`` may be either:
          - a plain dict snapshot of the current run (agent cards, budget, approvals), or
          - a callable returning that dict, so the gateway reflects live state on each
            /api/status poll without restarting the daemon.
        """
        self.budget_caps = dict(budget_caps or {})
        self.stopped = False
        self.templates: list[str] = []
        self.idle_timeout = idle_timeout_seconds
        self._clock = clock
        self.last_activity = self._clock()
        self._live_state = live_state
        self._session_to_run: dict[str, str] = {}

    def status(self) -> dict:
        data: dict = {"stopped": self.stopped, "budget_caps": dict(self.budget_caps)}
        # Link to a live run's snapshot if supplied
        live = self._live_state
        if live is not None:
            try:
                snap = live() if callable(live) else live
                if isinstance(snap, dict):
                    data["live"] = snap
            except Exception:
                pass
        return data

    def live_status(self) -> dict | None:
        """Return the live run snapshot (agents, budget, approvals), or None."""
        live = self._live_state
        if live is None:
            return None
        try:
            return live() if callable(live) else live
        except Exception:
            return None

    def attach_session(self, token: str) -> None:
        """Record which session token is talking to a run (for audit/linking)."""
        self._session_to_run[token] = str(time.time())

    def touch(self) -> None:
        self.last_activity = self._clock()

    def is_idle(self, now: float | None = None) -> bool:
        return (self._clock() if now is None else now) - self.last_activity > self.idle_timeout

    def pending_approvals(self) -> list:
        live = self.live_status()
        if isinstance(live, dict):
            return live.get("approvals") or []
        return []

    def approve(self, approval_id: str) -> bool:
        pending = self.pending_approvals()
        if not pending:
            return True
        for p in pending:
            if isinstance(p, dict) and p.get("id") == approval_id:
                return True
        return False

    def stop(self) -> None:
        self.stopped = True

    def lower_budget(self, cap: str, value: float) -> bool:
        """Only ever lower a cap; never raise it (the web page may only lower)."""
        if cap not in self.budget_caps:
            return False
        if value >= self.budget_caps[cap]:
            return False
        self.budget_caps[cap] = value
        return True

    def start_template(self, name: str) -> bool:
        if name not in self.templates:
            return False
        self.started = name
        return True
