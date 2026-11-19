"""Scan history store (SQLite) — powers history, diff, status, retest, gate.

Stores every Nightwing run, its findings, and the operator decision on each
finding (open / accepted / fixed / verified). Enables:
  - ``squad security history`` — list past runs
  - ``squad security diff <a> <b>`` — new / fixed findings between two runs
  - ``squad security status`` — live run + finding counts
  - ``squad security retest <finding-id>`` — re-run the phase for one finding
  - ``squad security gate --fail-on high`` — CI-friendly threshold check
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from squad.security_findings import SecurityFinding, redact_evidence

# Severity ranking for thresholds.
_SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def default_db_path() -> str:
    base = os.environ.get("SQUAD_DATA_DIR", os.path.join(os.path.expanduser("~"), "AppData", "Local", "squad"))
    Path(base).mkdir(parents=True, exist_ok=True)
    return os.path.join(base, "history.db")


class ScanStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or default_db_path()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    target TEXT NOT NULL,
                    phases TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    tool_coverage TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    description TEXT NOT NULL,
                    file_or_endpoint TEXT NOT NULL,
                    evidence_snippet TEXT NOT NULL DEFAULT '',
                    cwe TEXT NOT NULL DEFAULT '',
                    owasp_category TEXT NOT NULL DEFAULT '',
                    remediation TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id)")

    # -- writing -----------------------------------------------------------
    def new_run(self, target: str, phases: str, tool_coverage: dict | None = None) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, target, phases, started_at, tool_coverage) VALUES (?,?,?,?,?)",
                (
                    run_id,
                    target,
                    phases,
                    datetime.now(UTC).isoformat(),
                    json.dumps(tool_coverage or {}),
                ),
            )
        return run_id

    def finish_run(self, run_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET finished_at=? WHERE run_id=?",
                (datetime.now(UTC).isoformat(), run_id),
            )

    def add_findings(self, run_id: str, findings: Iterable[SecurityFinding]) -> int:
        n = 0
        with self._connect() as conn:
            for f in findings:
                conn.execute(
                    """INSERT INTO findings (id, run_id, tool, severity, description,
                       file_or_endpoint, evidence_snippet, cwe, owasp_category, remediation)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        uuid.uuid4().hex[:16],
                        run_id,
                        f.tool,
                        f.severity.value,
                        f.description,
                        f.file_or_endpoint,
                        redact_evidence(f.evidence_snippet),
                        f.cwe,
                        f.owasp_category,
                        f.remediation,
                    ),
                )
                n += 1
        return n

    def set_status(self, finding_id: str, status: str) -> bool:
        if status not in ("open", "accepted", "fixed", "verified"):
            raise ValueError(f"invalid status: {status}")
        with self._connect() as conn:
            cur = conn.execute("UPDATE findings SET status=? WHERE id=?", (status, finding_id))
            return cur.rowcount > 0

    def set_status_by_key(self, run_id: str, tool: str, endpoint: str, status: str) -> int:
        """Mark all matching findings in a run."""
        if status not in ("open", "accepted", "fixed", "verified"):
            raise ValueError(f"invalid status: {status}")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE findings SET status=? WHERE run_id=? AND tool=? AND file_or_endpoint=?",
                (status, run_id, tool, endpoint),
            )
            return cur.rowcount

    # -- reading -----------------------------------------------------------
    def runs(self, target: str | None = None, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            if target:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE target=? ORDER BY started_at DESC LIMIT ?",
                    (target, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def run_findings(self, run_id: str, status: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM findings WHERE run_id=? AND status=? ORDER BY severity",
                    (run_id, status),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM findings WHERE run_id=? ORDER BY severity", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def count_by_severity(self, run_id: str) -> dict[str, int]:
        counts = {s: 0 for s in ("critical", "high", "medium", "low", "info")}
        for f in self.run_findings(run_id):
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1
        return counts

    def status_summary(self) -> dict:
        """Run and finding counts by status, newest run overall risk."""
        runs = self.runs(limit=5)
        latest = runs[0]["run_id"] if runs else None
        return {
            "total_runs": len(self.runs(limit=1000)),
            "latest_run": latest,
            "latest_target": runs[0]["target"] if runs else None,
            "latest_severity": self.count_by_severity(latest) if latest else {},
            "open_by_run": {r["run_id"]: sum(1 for f in self.run_findings(r["run_id"]) if f["status"] == "open") for r in runs},
        }

    # -- diff --------------------------------------------------------------
    def diff(self, run_a: str, run_b: str) -> dict:
        """New / fixed findings between two runs, keyed on tool+endpoint+severity."""
        fa = {(f["tool"], f["file_or_endpoint"], f["severity"], f["description"]) for f in self.run_findings(run_a)}
        fb = {(f["tool"], f["file_or_endpoint"], f["severity"], f["description"]) for f in self.run_findings(run_b)}
        return {
            "run_a": run_a,
            "run_b": run_b,
            "new": sorted([list(k) for k in fb - fa]),
            "fixed": sorted([list(k) for k in fa - fb]),
        }

    # -- gate --------------------------------------------------------------
    def gate(self, run_id: str, fail_on: str = "high", ignore_statuses=("accepted", "verified", "fixed")) -> tuple[bool, list[dict]]:
        """Return (passed, blockers). A blocker is any finding at/above threshold not ignored."""
        threshold = _SEVERITY_RANK.get(fail_on, 3)
        blockers = [
            f for f in self.run_findings(run_id) if _SEVERITY_RANK.get(f["severity"], 0) >= threshold and f["status"] not in ignore_statuses
        ]
        return len(blockers) == 0, blockers


def store_for_testing(tmp_path) -> ScanStore:
    return ScanStore(os.path.join(str(tmp_path), "history.db"))
