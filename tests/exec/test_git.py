"""Tests for git hardening (hooks disabled, program-running config blanked)."""

import os
import subprocess

import pytest

from squad.exec import run_command
from squad.exec.git import hardened_git_args, hardened_git_env


def _git(cwd, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def test_hardened_git_args_disable_hooks():
    args = hardened_git_args()
    assert any(a.startswith("core.hooksPath=") for a in args)
    # The empty hooks directory must actually exist and be empty.
    hooks_path = next(a for a in args if a.startswith("core.hooksPath=")).split("=", 1)[1]
    assert os.path.isdir(hooks_path)
    assert os.listdir(hooks_path) == []


def test_hardened_git_args_blank_program_config():
    args = hardened_git_args()
    assert "core.sshCommand=" in args
    assert "core.askpass=" in args
    assert "core.fsmonitor=" in args
    assert "diff.external=" in args


def test_hardened_git_env_ignores_system_config():
    env = hardened_git_env()
    assert env.get("GIT_CONFIG_NOSYSTEM") == "1"
    assert "PATH" in env  # scrubbed but still runnable


@pytest.mark.skipif(os.name == "nt", reason="executable-bit hooks are POSIX")
def test_git_hooks_are_not_run(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "a@b.c")
    _git(repo, "config", "user.name", "tester")

    hooks = repo / ".git" / "hooks"
    (hooks / "pre-commit").write_text("#!/bin/sh\ntouch hook-ran.txt\n", encoding="utf-8")
    os.chmod(hooks / "pre-commit", 0o755)

    (repo / "file.txt").write_text("hi", encoding="utf-8")
    _git(repo, "add", "file.txt")

    result = run_command(
        ["git", *hardened_git_args(), "commit", "-m", "x"],
        cwd=str(repo),
        env=hardened_git_env(),
    )
    assert result.returncode == 0
    assert not (repo / "hook-ran.txt").exists()
