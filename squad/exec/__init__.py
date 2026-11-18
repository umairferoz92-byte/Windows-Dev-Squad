"""Executor package: OS-adapter, isolation enforcement, scrubbed env, git hardening."""

from __future__ import annotations

from squad.exec.adapter import OSAdapter, get_adapter
from squad.exec.env import SECRET_KEY_MARKERS, scrubbed_env
from squad.exec.git import hardened_git_args, hardened_git_env
from squad.exec.result import ProcessResult
from squad.exec.runner import MIN_AGENT_ISOLATION, IsolationError, run_command

__all__ = [
    "ProcessResult",
    "OSAdapter",
    "get_adapter",
    "run_command",
    "IsolationError",
    "MIN_AGENT_ISOLATION",
    "scrubbed_env",
    "SECRET_KEY_MARKERS",
    "hardened_git_args",
    "hardened_git_env",
]
