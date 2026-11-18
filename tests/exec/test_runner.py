"""Tests for the executor: isolation enforcement, arg-list-only, env scrubbing."""

import sys

import pytest

from squad.exec import IsolationError, run_command


def test_rejects_string_command():
    with pytest.raises(TypeError):
        run_command("echo hi")


def test_rejects_non_list_command():
    with pytest.raises(TypeError):
        run_command(123)


def test_rejects_empty_command():
    with pytest.raises(ValueError):
        run_command([])


def test_agent_code_at_level0_refused():
    with pytest.raises(IsolationError):
        run_command([sys.executable, "-c", "pass"], is_agent_code=True, isolation_level=0)


def test_agent_code_none_level_refused():
    with pytest.raises(IsolationError):
        run_command([sys.executable, "-c", "pass"], is_agent_code=True, isolation_level=None)


def test_agent_code_unavailable_level_refused():
    # Level 2 (Windows Sandbox) is not available on this machine.
    with pytest.raises(IsolationError):
        run_command([sys.executable, "-c", "pass"], is_agent_code=True, isolation_level=2)


def test_trusted_check_at_level0_runs():
    result = run_command([sys.executable, "-c", "print('ok')"], isolation_level=0)
    assert result.returncode == 0
    assert "ok" in result.stdout


def test_env_is_scrubbed(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    result = run_command(
        [sys.executable, "-c", "import os; print(os.environ.get('OPENROUTER_API_KEY', ''))"]
    )
    assert "sk-secret" not in result.stdout


def test_utf8_output():
    result = run_command([sys.executable, "-c", "print('héllo wörld')"])
    assert result.returncode == 0
    assert "héllo wörld" in result.stdout
