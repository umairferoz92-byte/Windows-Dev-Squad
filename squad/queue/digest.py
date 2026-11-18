"""Morning digest built from the overnight queue."""

from __future__ import annotations


def build_digest(jobs: list[dict]) -> str:
    pending = [job for job in jobs if job.get("status") == "pending"]
    done = [job for job in jobs if job.get("status") == "done"]
    lines = ["squad morning digest", "=" * 24, f"{len(done)} done, {len(pending)} pending"]
    for job in pending:
        lines.append(f"  [pending] {job['task']}")
    for job in done:
        lines.append(f"  [done] {job['task']} -> {job.get('result', '')}")
    return "\n".join(lines) + "\n"
