"""Run the golden task set with a fixed budget and record results per commit."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from squad.eval.tasks import GOLDEN_TASKS, GoldenTask


@dataclass
class EvalResult:
    task_id: str
    ok: bool
    cost: float
    steps: int
    failed_gates: list[str] = field(default_factory=list)
    refused_correctly: bool | None = None
    error: str = ""


def git_commit(cwd: Path) -> str:
    """Return the short HEAD commit (or 'none' if not a repo)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cwd), capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "none"
    except Exception:
        return "none"


class EvalStore:
    """SQLite store of per-commit eval results, so runs can be compared."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS eval ("
            " commit_sha TEXT, task_id TEXT, run_ts REAL, ok INTEGER, "
            " cost REAL, steps INTEGER, refused_correctly INTEGER,"
            " PRIMARY KEY(commit_sha, task_id))"
        )
        self._db.commit()

    def record(self, commit: str, r: EvalResult) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO eval VALUES (?,?,?,?,?,?,?)",
            (commit, r.task_id, time.time(), int(r.ok), r.cost, r.steps,
             None if r.refused_correctly is None else int(r.refused_correctly)),
        )
        self._db.commit()

    def summary(self, commit: str) -> dict:
        rows = self._db.execute(
            "SELECT task_id, ok, cost, steps FROM eval WHERE commit_sha=?", (commit,)
        ).fetchall()
        if not rows:
            return {"commit": commit, "runs": 0, "pass_rate": None, "cost": 0.0}
        return {
            "commit": commit,
            "runs": len(rows),
            "pass_rate": sum(1 for r in rows if r[1]) / len(rows),
            "cost": sum(r[2] for r in rows),
        }

    def close(self) -> None:
        self._db.close()


def run_eval(
    tasks,
    *,
    run_task,            # callable(task: GoldenTask) -> EvalResult
    repo_root: Path,
    store: EvalStore,
) -> list[EvalResult]:
    """Run every task through ``run_task`` and record results for the commit."""
    commit = git_commit(repo_root)
    results = []
    for task in tasks:
        r = run_task(task)
        store.record(commit, r)
        results.append(r)
    store.close()
    return results
