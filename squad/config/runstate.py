"""Durable run state: SQLite checkpoints so a crash never leaves a half-run.

After every agent step the current plan/step/branch/budget is written to SQLite
in the data folder. On start, unfinished runs are listed and the caller must
pick resume, rollback, or mark-failed — recovery is never silent.

State machine: RUNNING -> (resume) RUNNING / (rollback) ROLLED_BACK /
                       (mark-failed) FAILED. A run that was RUNNING when the
                       process died is offered again on the next start.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

STATES = ("RUNNING", "ROLLED_BACK", "FAILED", "DONE")


@dataclass
class RunState:
    run_id: str
    task: str
    plan: dict = field(default_factory=dict)
    step: int = 0
    branch: str = ""
    budget_used: float = 0.0
    status: str = "RUNNING"
    updated_at: float = 0.0


class RunStateStore:
    """SQLite store of per-step run checkpoints (data-dir sqlite, no pywin32)."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS runs ("
            " run_id TEXT PRIMARY KEY, task TEXT, plan TEXT, step INTEGER,"
            " branch TEXT, budget_used REAL, status TEXT, updated_at REAL)"
        )
        self._db.commit()

    def checkpoint(self, rs: RunState) -> None:
        """Write the run state after a step. idempotent per run_id."""
        rs.updated_at = time.time()
        self._db.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)",
            (rs.run_id, rs.task, json.dumps(rs.plan), rs.step, rs.branch,
             rs.budget_used, rs.status, rs.updated_at),
        )
        self._db.commit()

    def get(self, run_id: str) -> RunState | None:
        row = self._db.execute(
            "SELECT run_id, task, plan, step, branch, budget_used, status, updated_at "
            "FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if not row:
            return None
        return RunState(run_id=row[0], task=row[1], plan=json.loads(row[2]),
                        step=row[3], branch=row[4], budget_used=row[5],
                        status=row[6], updated_at=row[7])

    def unfinished(self) -> list[RunState]:
        """Runs still RUNNING (i.e. a process died mid-run)."""
        rows = self._db.execute(
            "SELECT run_id, task, plan, step, branch, budget_used, status, updated_at "
            "FROM runs WHERE status='RUNNING' ORDER BY updated_at"
        ).fetchall()
        return [RunState(run_id=r[0], task=r[1], plan=json.loads(r[2]), step=r[3],
                         branch=r[4], budget_used=r[5], status=r[6], updated_at=r[7])
                for r in rows]

    def resume(self, run_id: str) -> RunState | None:
        rs = self.get(run_id)
        if rs and rs.status == "RUNNING":
            return rs
        return None

    def rollback(self, run_id: str) -> None:
        self._transition(run_id, "ROLLED_BACK")

    def mark_failed(self, run_id: str) -> None:
        self._transition(run_id, "FAILED")

    def mark_done(self, run_id: str) -> None:
        self._transition(run_id, "DONE")

    def _transition(self, run_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE runs SET status=?, updated_at=? WHERE run_id=?",
            (status, time.time(), run_id),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()


# The three allowed terminal resolutions of a crash: resume, rollback, mark-failed.
def resolve_crash(store: RunStateStore, run_id: str, choice: str) -> RunState | None:
    """Handle an unfinished run. Never resume silently.

    choice: 'resume' | 'rollback' | 'mark-failed'
    """
    if choice == "resume":
        return store.resume(run_id)
    if choice == "rollback":
        store.rollback(run_id)
        return None
    if choice == "mark-failed":
        store.mark_failed(run_id)
        return None
    raise ValueError(f"unknown recovery choice: {choice}")
