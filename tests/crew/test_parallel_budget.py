"""Tests for a shared task budget across parallel agents."""

import pytest

from squad.budget import BudgetError, BudgetLimits, BudgetManager, PriceTable

PRICES = PriceTable({"models": {"m": {"input": 1000.0, "output": 0.0}}})


def test_shared_task_budget_refuses_when_exceeded():
    budget = BudgetManager(BudgetLimits(per_task=0.002), PRICES)  # $0.002 shared task cap
    est1 = budget.preflight("ironman", "openrouter", "m", 1, 0)  # 0.001
    est2 = budget.preflight("tester", "openrouter", "m", 1, 0)  # 0.001 (not spent yet)
    budget.record(est1, "ironman", "openrouter")
    budget.record(est2, "tester", "openrouter")  # task spent = 0.002
    with pytest.raises(BudgetError):
        budget.preflight("quality", "openrouter", "m", 1, 0)  # would hit 0.003 > 0.002


def test_per_agent_limits_are_independent():
    budget = BudgetManager(BudgetLimits(per_agent=0.0015), PRICES)
    est1 = budget.preflight("ironman", "openrouter", "m", 1, 0)
    budget.record(est1, "ironman", "openrouter")  # ironman spent 0.001
    # tester has its own 0.0015 budget, unaffected by ironman
    est2 = budget.preflight("tester", "openrouter", "m", 1, 0)
    assert est2.estimated_cost > 0
    # ironman cannot exceed its own cap
    with pytest.raises(BudgetError):
        budget.preflight("ironman", "openrouter", "m", 1, 0)
