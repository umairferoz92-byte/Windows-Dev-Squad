"""Tests for running check commands under the guard."""

import sys

import pytest

from squad.checks.check import run_checks
from squad.guard import Policy


def test_run_checks_runs_configured_command(tmp_path):
    repo_config = {"repo": {"check_commands": {"test": [sys.executable, "-c", "print('ok')"]}}}
    results = run_checks(repo_config, Policy(), str(tmp_path))
    assert len(results) == 1
    assert results[0].name == "test"
    assert results[0].passed is True
    assert "ok" in results[0].stdout


def test_run_checks_trusted_runs_at_level0(tmp_path):
    # run_tests requires isolation level 1 for agent code; trusted check at
    # level 0 must still be allowed.
    repo_config = {"repo": {"check_commands": {"test": [sys.executable, "-c", "pass"]}}}
    results = run_checks(repo_config, Policy(), str(tmp_path))
    assert results[0].verdict == "allow"
    assert results[0].passed is True


def test_run_checks_skips_unconfigured(tmp_path):
    repo_config = {"repo": {"check_commands": {}}}
    assert run_checks(repo_config, Policy(), str(tmp_path)) == []


def test_run_checks_resolves_python_interpreter(tmp_path):
    repo_config = {"repo": {"check_commands": {"test": ["python", "-c", "print('x')"]}}}
    results = run_checks(repo_config, Policy(), str(tmp_path))
    assert results[0].passed is True


def test_run_checks_rejects_string_command(tmp_path):
    repo_config = {"repo": {"check_commands": {"test": "pytest -q"}}}
    with pytest.raises(ValueError):
        run_checks(repo_config, Policy(), str(tmp_path))


def test_run_checks_denied_when_guard_blocks(tmp_path):
    # Empty tools table -> run_tests is unknown -> default-deny (ASK), not run.
    policy = Policy({"tools": {}})
    repo_config = {"repo": {"check_commands": {"test": [sys.executable, "-c", "pass"]}}}
    results = run_checks(repo_config, policy, str(tmp_path))
    assert results[0].verdict == "ask"
    assert results[0].returncode is None
