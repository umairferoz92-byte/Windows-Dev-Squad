"""Smoke tests for the squad CLI."""

from typer.testing import CliRunner

from squad import __version__
from squad.cli.app import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_doctor_runs():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Isolation" in result.output


def test_doctor_setup_help():
    result = runner.invoke(app, ["doctor", "--setup-help"])
    assert result.exit_code == 0
    assert "New-LocalUser" in result.output


def test_check_with_temp_config(tmp_path):
    cfg = tmp_path / "squad.yaml"
    cfg.write_text("repo:\n  check_commands:\n    test: ['python', '-c', \"print('hi')\"]\n", encoding="utf-8")
    guard = tmp_path / "guard.yaml"
    guard.write_text("version: 1\n", encoding="utf-8")
    result = runner.invoke(app, ["check", "--config", str(cfg), "--guard", str(guard)])
    assert result.exit_code == 0
    assert "[PASS]" in result.output


def test_cost_empty_ledger(tmp_path):
    result = runner.invoke(app, ["cost", "--ledger", str(tmp_path / "l.sqlite3")])
    assert result.exit_code == 0
    assert "Cost by day" in result.output


def test_cost_reconcile(tmp_path):
    from squad.budget import Ledger

    path = str(tmp_path / "l.sqlite3")
    ledger = Ledger(path)
    ledger.record("r", "a", "openrouter", "m", 1, 1, 0, 10.0, 1000.0)
    ledger.close()

    result = runner.invoke(app, ["cost", "--reconcile", "openrouter=10.0", "--ledger", path])
    assert result.exit_code == 0
    assert "ok" in result.output
