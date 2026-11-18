"""Git hardening: run git with hooks disabled and program-running config blanked.

Repo-level git config can run arbitrary programs (core.sshCommand, core.askpass,
core.fsmonitor, diff.external, hooks). The hardened prefix disables these and
points core.hooksPath at an empty directory, so `git commit` etc. cannot execute
repo- or config-controlled code.
"""

from __future__ import annotations

import tempfile

from squad.exec.env import scrubbed_env

_hooks_dir: str | None = None


def _empty_hooks_dir() -> str:
    global _hooks_dir
    if _hooks_dir is None:
        _hooks_dir = tempfile.mkdtemp(prefix="squad-empty-hooks-")
    return _hooks_dir


def hardened_git_args() -> list[str]:
    return [
        "-c",
        f"core.hooksPath={_empty_hooks_dir()}",
        "-c",
        "core.sshCommand=",
        "-c",
        "core.askpass=",
        "-c",
        "core.fsmonitor=",
        "-c",
        "diff.external=",
    ]


def hardened_git_env() -> dict[str, str]:
    env = scrubbed_env()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env
