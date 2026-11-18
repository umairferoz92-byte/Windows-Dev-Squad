"""Tests for the budget manager: refuse before send, warn, worst-case usage, spike."""

import pytest

from squad.budget import BudgetError, BudgetLimits, BudgetManager, Ledger, PriceTable

PRICES = PriceTable(
    {
        "as_of": "2026-11-03",
        "models": {
            "openrouter/test/model": {"input": 1.0, "output": 2.0},
        },
    }
)

MODEL = "openrouter/test/model"


def _manager(**kwargs):
    return BudgetManager(BudgetLimits(**kwargs), PRICES)


def test_unknown_model_blocked():
    with pytest.raises(BudgetError):
        _manager().preflight("a", "openrouter", "unknown/model", 100, 100)


def test_per_call_input_cap_refused():
    with pytest.raises(BudgetError):
        _manager(per_call_input_tokens=100).preflight("a", "openrouter", MODEL, 101, 10)


def test_per_call_output_cap_refused():
    with pytest.raises(BudgetError):
        _manager(per_call_output_tokens=50).preflight("a", "openrouter", MODEL, 10, 51)


def test_preflight_cost_estimate():
    est = _manager().preflight("a", "openrouter", MODEL, 1000, 1000)
    assert est.estimated_cost == pytest.approx(1000 / 1e6 * 1.0 + 1000 / 1e6 * 2.0)


def test_agent_cap_exceeded_on_fourth_call():
    m = _manager(per_agent=0.003)
    for _ in range(3):
        est = m.preflight("coder", "openrouter", MODEL, 1000, 0)  # 0.001 each
        m.record(est, "coder", "openrouter")
    with pytest.raises(BudgetError):
        m.preflight("coder", "openrouter", MODEL, 1000, 0)  # would reach 0.004 > 0.003


def test_unreported_usage_counts_worst_case(tmp_path):
    ledger = Ledger(str(tmp_path / "l.sqlite3"))
    m = BudgetManager(BudgetLimits(per_agent=1.0), PRICES, ledger=ledger, clock=lambda: 1000.0)
    est = m.preflight("a", "openrouter", MODEL, 1000, 1000)
    m.record(est, "a", "openrouter", run_id="r1")  # no reported usage -> worst case
    ledger.close()

    ledger2 = Ledger(str(tmp_path / "l.sqlite3"))
    rows = ledger2.totals("task")
    assert rows[0]["cost"] == pytest.approx(est.estimated_cost)
    assert rows[0]["tokens_in"] == 1000
    assert rows[0]["tokens_out"] == 1000
    ledger2.close()


def test_warns_at_50_and_80_percent():
    m = _manager(per_agent=0.001)
    est1 = m.preflight("a", "openrouter", MODEL, 500, 0)  # cost 0.0005 -> 50%
    assert m.last_warning == "per_agent at 50% of limit"
    m.record(est1, "a", "openrouter")
    m.preflight("a", "openrouter", MODEL, 300, 0)  # total 0.0008 -> 80%
    assert m.last_warning == "per_agent at 80% of limit"


def test_spike_breaker_pauses():
    clock = [1000.0]
    m = BudgetManager(
        BudgetLimits(spike_window_seconds=300, spike_limit=0.002), PRICES, clock=lambda: clock[0]
    )
    est = m.preflight("a", "openrouter", MODEL, 1000, 0)  # 0.001
    for t in (1000.0, 1010.0, 1020.0):
        clock[0] = t
        m.record(est, "a", "openrouter")
    assert m.paused is True
    with pytest.raises(BudgetError):
        m.preflight("a", "openrouter", MODEL, 10, 0)


def test_paused_blocks_preflight():
    m = _manager()
    m._paused = True
    with pytest.raises(BudgetError):
        m.preflight("a", "openrouter", MODEL, 10, 0)
