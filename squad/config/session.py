"""Crash-recovery run session (Phase 12): atomic, resumable."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path


def default_session_path() -> str:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "squad", "session.json")


class Session:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def start(self, task: str, crew) -> dict:
        state = {
            "run_id": uuid.uuid4().hex,
            "task": task,
            "crew": crew,
            "started_at": time.time(),
            "phase": "plan",
            "status": "running",
        }
        self.save(state)
        return state

    def save(self, state: dict) -> None:
        # Write atomically so a crash cannot leave a corrupt session file.
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix="session-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def resume(self) -> dict | None:
        return self.load()

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
