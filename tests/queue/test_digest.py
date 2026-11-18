"""Tests for the morning digest."""

from squad.queue import build_digest


def test_digest_lists_pending_and_done():
    jobs = [
        {"task": "a", "status": "pending"},
        {"task": "b", "status": "done", "result": "ok"},
    ]
    text = build_digest(jobs)
    assert "1 done, 1 pending" in text
    assert "[pending] a" in text
    assert "[done] b -> ok" in text
