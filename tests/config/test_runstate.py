"""Durable run state and recovery (Feature 5): crash always lands in a known state."""

import pytest

from squad.config.runstate import (
    STATES,
    RunState,
    RunStateStore,
    resolve_crash,
)


def test_checkpoint_then_get(tmp_path):
    s = RunStateStore(tmp_path / "runs.sqlite")
    rs = RunState(
        run_id="r1",
        task="fix test",
        plan={"phases": ["a", "b"]},
        step=2,
        branch="feature/x",
        budget_used=0.4,
    )
    s.checkpoint(rs)
    got = s.get("r1")
    assert got.step == 2
    assert got.plan == {"phases": ["a", "b"]}
    assert got.status == "RUNNING"


def test_checkpoint_overwrites_later_step(tmp_path):
    s = RunStateStore(tmp_path / "runs.sqlite")
    s.checkpoint(RunState(run_id="r1", task="t", step=1))
    s.checkpoint(RunState(run_id="r1", task="t", step=4))
    assert s.get("r1").step == 4


def test_unfinished_lists_only_running(tmp_path):
    s = RunStateStore(tmp_path / "runs.sqlite")
    s.checkpoint(RunState(run_id="a", task="t", step=1))  # RUNNING
    s.checkpoint(RunState(run_id="b", task="t", step=1))  # RUNNING
    s.mark_failed("b")
    assert [r.run_id for r in s.unfinished()] == ["a"]


def test_crash_always_resolves_to_one_of_three_states(tmp_path):
    """Killing the process at a random point ends in resume/rollback/mark-failed."""
    s = RunStateStore(tmp_path / "runs.sqlite")
    # simulate a process that died at a random step: the run is still RUNNING
    s.checkpoint(RunState(run_id="crash", task="t", step=3))
    crashed = s.get("crash")
    assert crashed.status == "RUNNING"  # not resolved yet

    for choice in ("resume", "rollback", "mark-failed"):
        s2 = RunStateStore(tmp_path / "runs.sqlite")  # fresh handle like a new process
        r = resolve_crash(s2, "crash", choice)
        final = s2.get("crash").status
        # resume keeps it RUNNING and returns it; others terminal-state it
        if choice == "resume":
            assert r is not None and final == "RUNNING"
        else:
            assert r is None and final in ("ROLLED_BACK", "FAILED")
        assert final in STATES


def test_recovery_is_never_silent_unknown_choice(tmp_path):
    s = RunStateStore(tmp_path / "runs.sqlite")
    with pytest.raises(ValueError):
        resolve_crash(s, "x", "do-whatever")


def test_resume_refuses_done_runs(tmp_path):
    s = RunStateStore(tmp_path / "runs.sqlite")
    s.checkpoint(RunState(run_id="done", task="t", step=1))
    s.mark_done("done")
    assert s.resume("done") is None
