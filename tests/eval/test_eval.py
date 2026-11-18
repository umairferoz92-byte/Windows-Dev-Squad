"""Tests for the evaluation harness (Feature 2)."""
import json
import sqlite3
from pathlib import Path

from squad.eval.runner import EvalResult, EvalStore, git_commit, run_eval
from squad.eval.tasks import GOLDEN_TASKS, GoldenTask, build_injection_repo


def test_golden_set_has_required_shape():
    assert len(GOLDEN_TASKS) >= 5
    for t in GOLDEN_TASKS:
        assert t.id and t.prompt and t.description
        assert t.budget_cap > 0


def test_store_records_and_summarizes(tmp_path):
    store = EvalStore(tmp_path / "eval.sqlite")
    store.record("abc123", EvalResult("eval-001", ok=True, cost=0.5, steps=3))
    store.record("abc123", EvalResult("eval-002", ok=False, cost=0.2, steps=2))
    s = store.summary("abc123")
    assert s["runs"] == 2
    assert s["pass_rate"] == 0.5
    assert s["cost"] == pytest_approx(0.7)
    store.close()


def pytest_approx(v):
    from pytest import approx
    return approx(v)


def test_run_eval_runs_each_task_and_stores_per_commit(tmp_path):
    store = EvalStore(tmp_path / "e.sqlite")
    calls = []

    def run_task(t: GoldenTask) -> EvalResult:
        calls.append(t.id)
        return EvalResult(t.id, ok=True, cost=0.01, steps=1)

    run_eval(GOLDEN_TASKS[:2], run_task=run_task, repo_root=tmp_path, store=store)
    assert calls == [GOLDEN_TASKS[0].id, GOLDEN_TASKS[1].id]
    # persisted to the store (reopen to confirm durable)
    s = EvalStore(tmp_path / "e.sqlite")
    assert s.summary(git_commit(tmp_path))["runs"] == 2


def test_build_injection_repo_creates_injection_file(tmp_path):
    inj = build_injection_repo(tmp_path)
    text = (inj / "README.md").read_text(encoding="utf-8")
    assert "SYSTEM OVERRIDE" in text
