"""Retention: partition entries (audit/ledger) by age for archiving."""
from __future__ import annotations

import json
import time
from pathlib import Path


def partition_by_age(
    entries: list[dict], max_age_days: int, now: float | None = None
) -> tuple[list[dict], list[dict]]:
    """Return (keep, archive): entries within max_age_days stay, older ones go to the archive."""
    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    keep = [entry for entry in entries if entry.get("timestamp", 0) >= cutoff]
    archived = [entry for entry in entries if entry.get("timestamp", 0) < cutoff]
    return keep, archived


def default_max_age_days() -> int:
    """Default retention window for audit/ledger entries."""
    return 365


def archive_audit(log_path: str | Path, max_age_days: int | None = None) -> int:
    """Archive audit entries older than ``max_age_days`` from a JSONL audit log.

    Old entries are moved out of the live log into a sibling
    ``<name>.archive.jsonl`` file (same JSONL format). Returns how many entries
    were archived. The live log is rewritten in place with only the kept lines.
    """
    max_age_days = max_age_days if max_age_days is not None else default_max_age_days()
    path = Path(log_path)
    if not path.exists():
        return 0
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            entries.append(obj)
    if not entries:
        return 0
    keep, archived = partition_by_age(entries, max_age_days)
    if not archived:
        return 0
    with path.open("w", encoding="utf-8") as fh:
        for entry in keep:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    archive_path = path.with_name(path.name + ".archive.jsonl")
    with archive_path.open("a", encoding="utf-8") as fh:
        for entry in archived:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return len(archived)
