"""Overnight job queue (file-based) and the morning digest."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path


def default_queue_path() -> str:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "squad", "queue.jsonl")


class JobQueue:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def enqueue(self, task: str, *, agent: str | None = None, enqueued_at: float | None = None) -> dict:
        job = {
            "id": uuid.uuid4().hex,
            "task": task,
            "agent": agent,
            "status": "pending",
            "enqueued_at": enqueued_at if enqueued_at is not None else time.time(),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(job, sort_keys=True) + "\n")
        return job

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def pending(self) -> list[dict]:
        return [job for job in self.load() if job.get("status") == "pending"]

    def mark_done(self, job_id: str, result: str | None = None) -> None:
        jobs = self.load()
        for job in jobs:
            if job["id"] == job_id:
                job["status"] = "done"
                job["result"] = result
                job["completed_at"] = time.time()
        self._write(jobs)

    def _write(self, jobs: list[dict]) -> None:
        with self.path.open("w", encoding="utf-8") as fh:
            for job in jobs:
                fh.write(json.dumps(job, sort_keys=True) + "\n")
