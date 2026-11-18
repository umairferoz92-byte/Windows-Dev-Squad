"""Tests for the crash-recovery session."""

from squad.config import Session


def test_start_load_resume(tmp_path):
    session = Session(str(tmp_path / "session.json"))
    state = session.start("task", ["a", "b"])
    assert session.load()["run_id"] == state["run_id"]
    assert session.resume()["task"] == "task"
    assert session.resume()["status"] == "running"


def test_save_then_clear(tmp_path):
    session = Session(str(tmp_path / "session.json"))
    session.start("task", [])
    session.clear()
    assert session.load() is None


def test_load_missing(tmp_path):
    session = Session(str(tmp_path / "nope.json"))
    assert session.load() is None
