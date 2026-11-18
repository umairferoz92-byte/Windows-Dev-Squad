"""Tests for the RemoteController (budgets can only be lowered)."""

from squad.gateway.controller import RemoteController


def test_lower_budget_ok():
    ctrl = RemoteController(budget_caps={"per_day": 5.0})
    assert ctrl.lower_budget("per_day", 2.0) is True
    assert ctrl.budget_caps["per_day"] == 2.0


def test_cannot_raise_budget():
    ctrl = RemoteController(budget_caps={"per_day": 5.0})
    assert ctrl.lower_budget("per_day", 8.0) is False
    assert ctrl.budget_caps["per_day"] == 5.0


def test_unknown_cap_rejected():
    ctrl = RemoteController(budget_caps={})
    assert ctrl.lower_budget("per_month", 1.0) is False


def test_stop_and_start_template():
    ctrl = RemoteController()
    ctrl.templates = ["t1"]
    ctrl.stop()
    assert ctrl.stopped is True
    assert ctrl.start_template("t1") is True
    assert ctrl.start_template("missing") is False


def test_idle_after_timeout():
    now = [1000.0]
    ctrl = RemoteController(idle_timeout_seconds=10, clock=lambda: now[0])
    assert ctrl.is_idle() is False
    now[0] += 11
    assert ctrl.is_idle() is True
    ctrl.touch()
    now[0] += 1
    assert ctrl.is_idle() is False
