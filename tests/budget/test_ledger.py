"""Tests for the append-only SQLite ledger."""

import pytest

from squad.budget import Ledger


def test_ledger_record_totals_and_groups(tmp_path):
    ledger = Ledger(str(tmp_path / "ledger.sqlite3"))
    ledger.record("r1", "coder", "openrouter", "m1", 100, 50, 0, 0.0001, 1000.0)
    ledger.record("r2", "coder", "openrouter", "m1", 200, 60, 0, 0.0002, 2000.0)
    ledger.record("r2", "tester", "openrouter", "m2", 300, 70, 0, 0.0003, 2100.0)

    assert ledger.total_cost() == pytest.approx(0.0006)
    assert ledger.total_cost("openrouter") == pytest.approx(0.0006)

    by_agent = {r["key"]: r["cost"] for r in ledger.totals("agent")}
    assert by_agent["coder"] == pytest.approx(0.0003)
    assert by_agent["tester"] == pytest.approx(0.0003)

    by_task = {r["key"]: r["cost"] for r in ledger.totals("task")}
    assert by_task["r2"] == pytest.approx(0.0005)
    ledger.close()


def test_ledger_unknown_grouping_raises(tmp_path):
    ledger = Ledger(str(tmp_path / "l.sqlite3"))
    with pytest.raises(ValueError):
        ledger.totals("bogus")
    ledger.close()
