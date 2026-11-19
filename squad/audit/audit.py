"""Append-only, hash-chained audit log (rule 10)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


def default_audit_path() -> str:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "squad", "audit.jsonl")


def _payload(entry: dict) -> str:
    return json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True)


def _hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256((prev_hash + _payload(entry)).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries = self._load()

    def _load(self) -> list[dict]:
        """Load chained entries, self-healing from truncated/partial writes.

        A line that is not a dict with a ``hash`` key is treated as a crash
        artifact (e.g. a write interrupted mid-line) and dropped, so the chain
        stays appendable. Any dropped line breaks the hash chain at that point,
        which ``verify`` still surfaces as a mismatch on the next good entry.
        """
        if not self.path.exists():
            return []
        entries = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("hash"), str):
                entries.append(obj)
        return entries

    def append(self, event: str, **fields) -> dict:
        prev = self._entries[-1]["hash"] if self._entries else ""
        entry = {"event": event, "timestamp": time.time(), "prev_hash": prev, **fields}
        entry["hash"] = _hash(prev, entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        self._entries.append(entry)
        return entry

    @property
    def latest_hash(self) -> str:
        return self._entries[-1]["hash"] if self._entries else ""

    def entries(self) -> list[str]:
        """Return raw log lines (one JSON object per line) for audit export."""
        if not self.path.exists():
            return []
        return [ln for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def verify(self) -> bool:
        prev = ""
        for entry in self._entries:
            if entry.get("prev_hash") != prev:
                return False
            if entry.get("hash") != _hash(entry.get("prev_hash", ""), entry):
                return False
            prev = entry["hash"]
        return True
