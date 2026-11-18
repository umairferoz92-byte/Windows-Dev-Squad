"""Concrete Tier 0 tools, built on the executor with hardened git."""

from __future__ import annotations

from squad.exec import ProcessResult, run_command
from squad.exec.git import hardened_git_args, hardened_git_env


def git_status(cwd: str, timeout: float = 15.0) -> ProcessResult:
    return run_command(
        ["git", *hardened_git_args(), "status", "--porcelain"],
        cwd=cwd,
        timeout=timeout,
        env=hardened_git_env(),
    )


def git_diff(cwd: str, timeout: float = 15.0) -> ProcessResult:
    return run_command(
        ["git", *hardened_git_args(), "diff", "--", "."],
        cwd=cwd,
        timeout=timeout,
        env=hardened_git_env(),
    )


def read_file(path: str, encoding: str = "utf-8") -> str:
    with open(path, encoding=encoding) as fh:
        return fh.read()
