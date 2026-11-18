"""Append-only SQLite cost ledger."""

from __future__ import annotations

import os
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    agent TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost REAL NOT NULL,
    recorded_at REAL NOT NULL
)
"""

_GROUPINGS = {
    "agent": "agent",
    "task": "run_id",
    "day": "date(recorded_at, 'unixepoch')",
    "provider": "provider",
}


def default_ledger_path() -> str:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "squad", "ledger.sqlite3")


class Ledger:
    def __init__(self, path: str):
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def record(
        self,
        run_id,
        agent,
        provider,
        model,
        tokens_in,
        tokens_out,
        cached_tokens,
        estimated_cost,
        recorded_at,
    ) -> None:
        self._conn.execute(
            "INSERT INTO usage (run_id, agent, provider, model, tokens_in, tokens_out,"
            " cached_tokens, estimated_cost, recorded_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                agent,
                provider,
                model,
                tokens_in,
                tokens_out,
                cached_tokens,
                estimated_cost,
                recorded_at,
            ),
        )
        self._conn.commit()

    def totals(self, grouping: str) -> list[dict]:
        expr = _GROUPINGS.get(grouping)
        if expr is None:
            raise ValueError(f"unknown grouping '{grouping}' (use one of {sorted(_GROUPINGS)})")
        # expr comes from the module-level _GROUPINGS whitelist, never user input.
        query = (
            f"SELECT {expr} AS key, SUM(estimated_cost), SUM(tokens_in), SUM(tokens_out) "
            f"FROM usage GROUP BY {expr}"  # nosec B608
        )
        rows = self._conn.execute(query).fetchall()
        return [
            {"key": r[0], "cost": r[1] or 0.0, "tokens_in": r[2] or 0, "tokens_out": r[3] or 0}
            for r in rows
        ]

    def total_cost(self, provider: str | None = None) -> float:
        if provider is None:
            row = self._conn.execute("SELECT SUM(estimated_cost) FROM usage").fetchone()
        else:
            row = self._conn.execute(
                "SELECT SUM(estimated_cost) FROM usage WHERE provider = ?", (provider,)
            ).fetchone()
        return float(row[0] or 0.0)

    def prune(self, max_age_days: int, now: float | None = None) -> int:
        """Delete ledger rows older than ``max_age_days`` (retention). Returns count."""
        import time as _time

        cutoff = (_time.time() if now is None else now) - max_age_days * 86400
        cur = self._conn.execute(
            "DELETE FROM usage WHERE recorded_at < ?", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
