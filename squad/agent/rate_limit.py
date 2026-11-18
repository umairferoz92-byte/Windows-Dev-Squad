"""Global rate limiter and kill-switch registry (Prompt 4).

Provides:
- ``RateLimiter``: a token-bucket/interval limiter shared across all active
  scanning tools, with a conservative default.
- ``KillSwitch``: a global registry that tracks running scan processes so
  ``squad security stop <run-id>`` can terminate them immediately.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateLimiter:
    """Interval-based limiter: at most one request per ``interval`` seconds.

    ``min_interval`` is the seconds between requests; the conservative default
    (0.5s -> ~2 req/sec) avoids hammering a target.
    """

    min_interval: float = 0.5  # conservative: 2 requests/second max

    _last: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self) -> None:
        """Block until the next request slot is available."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last = time.monotonic()

    def set_rate(self, requests_per_sec: float) -> None:
        if requests_per_sec <= 0:
            raise ValueError("requests_per_sec must be > 0")
        self.min_interval = 1.0 / requests_per_sec


class KillSwitch:
    """Global registry of running scan runs, keyed by run_id.

    ``squad security stop <run-id>`` calls ``terminate`` on the registry,
    which kills every tracked child process.
    """

    def __init__(self) -> None:
        self._procs: dict[str, list[subprocess.Popen]] = {}
        self._lock = threading.Lock()

    def new_run(self) -> str:
        run_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._procs[run_id] = []
        return run_id

    def register(self, run_id: str, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.setdefault(run_id, []).append(proc)

    def terminate(self, run_id: str) -> int:
        """Kill all child processes for a run. Returns the count terminated."""
        with self._lock:
            procs = self._procs.pop(run_id, [])
        count = 0
        for proc in procs:
            if proc.poll() is None:  # still running
                try:
                    proc.terminate()
                    proc.wait(timeout=1.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                count += 1
        return count

    def active(self) -> dict[str, int]:
        with self._lock:
            return {rid: len(procs) for rid, procs in self._procs.items()}


# A single shared instance used by Nightwing Phase C.
GLOBAL_RATE_LIMITER = RateLimiter()
GLOBAL_KILL_SWITCH = KillSwitch()
