"""The executor: run commands with isolation enforcement and a scrubbed env.

Every command is an argument list (never a shell string). Agent code is
refused unless a real isolation level (>= 1) is requested and available, so
agent code never runs in the user's own account.
"""

from __future__ import annotations

from squad.exec.adapter import OSAdapter, get_adapter
from squad.exec.env import scrubbed_env
from squad.exec.result import ProcessResult

MIN_AGENT_ISOLATION = 1


class IsolationError(RuntimeError):
    """Raised when agent code would run without sufficient isolation."""


def run_command(
    cmd,
    *,
    cwd: str | None = None,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
    isolation_level: int | None = 0,
    is_agent_code: bool = False,
    adapter: OSAdapter | None = None,
) -> ProcessResult:
    if isinstance(cmd, str):
        raise TypeError("command must be an argument list, never a string (no shell)")
    if not isinstance(cmd, (list, tuple)):
        raise TypeError("command must be a list or tuple of arguments")
    if not cmd:
        raise ValueError("command must not be empty")

    ad = adapter or get_adapter()

    if is_agent_code:
        if isolation_level is None or isolation_level < MIN_AGENT_ISOLATION:
            raise IsolationError(
                "agent code must never run in the user's own account "
                f"(requested level {isolation_level}, minimum {MIN_AGENT_ISOLATION})"
            )
        if not ad.supports_isolation(isolation_level):
            raise IsolationError(
                f"isolation level {isolation_level} is not available on this machine"
            )

    final_env = scrubbed_env()
    if env:
        final_env.update(env)
    # Force UTF-8 for all subprocess I/O (spec requirement).
    final_env["PYTHONUTF8"] = "1"
    final_env["PYTHONIOENCODING"] = "utf-8"
    # Pass the isolation level down so WindowsAdapter can launch under a
    # low-privilege user (level 1) or Windows Sandbox (level 2).
    try:
        return ad.run(
            list(cmd),
            cwd=cwd,
            env=final_env,
            timeout=timeout,
            isolation_level=isolation_level,
        )
    except TypeError:
        # Adapter predates the isolation kwarg; fall back to a plain run.
        return ad.run(list(cmd), cwd=cwd, env=final_env, timeout=timeout)
