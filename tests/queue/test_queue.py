"""Tests for the overnight job queue."""

from squad.queue import JobQueue


def test_enqueue_and_load(tmp_path):
    queue = JobQueue(str(tmp_path / "q.jsonl"))
    job = queue.enqueue("fix bug")
    assert job["status"] == "pending"
    assert queue.load()[0]["task"] == "fix bug"


def test_pending_filters(tmp_path):
    queue = JobQueue(str(tmp_path / "q.jsonl"))
    job = queue.enqueue("a")
    queue.enqueue("b")
    assert len(queue.pending()) == 2
    queue.mark_done(job["id"], result="ok")
    assert len(queue.pending()) == 1
    done = [j for j in queue.load() if j["status"] == "done"]
    assert done[0]["result"] == "ok"


def test_empty_queue(tmp_path):
    queue = JobQueue(str(tmp_path / "q.jsonl"))
    assert queue.load() == []
    assert queue.pending() == []
