"""Parallel crew execution: run jobs concurrently up to max_running.

Each job is one agent's work (already bounded by its own per-agent budget);
a shared per-task budget is enforced by the BudgetManager's per_task layer.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


def run_parallel(jobs: list[Callable[[], object]], max_running: int) -> list[object]:
    """Run ``jobs`` concurrently with at most ``max_running`` in flight, in order."""
    if not jobs:
        return []
    with ThreadPoolExecutor(max_workers=max(1, max_running)) as pool:
        return list(pool.map(lambda job: job(), jobs))
