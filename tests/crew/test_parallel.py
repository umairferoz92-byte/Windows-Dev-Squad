"""Tests for parallel execution with max_running."""

import threading
import time

from squad.crew import run_parallel


def test_run_parallel_respects_max_running():
    lock = threading.Lock()
    active = 0
    max_active = 0

    def job():
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "done"

    results = run_parallel([job] * 5, max_running=2)
    assert len(results) == 5
    assert all(r == "done" for r in results)
    assert max_active <= 2


def test_run_parallel_preserves_order():
    results = run_parallel([lambda i=i: i for i in range(3)], max_running=2)
    assert results == [0, 1, 2]


def test_run_parallel_empty():
    assert run_parallel([], max_running=2) == []
