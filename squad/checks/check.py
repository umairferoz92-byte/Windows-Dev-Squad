"""Run configured check commands (test/lint/typecheck/security scan) under the guard."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from squad.exec import ProcessResult, run_command
from squad.guard import Policy, ToolRequest, Verdict, evaluate

CHECK_TOOLS = {
    "test": "run_tests",
    "lint": "run_lint",
    "typecheck": "run_typecheck",
    "security_scan": "run_security_scan",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    tool: str
    command: tuple[str, ...]
    verdict: str
    returncode: int | None
    timed_out: bool
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.verdict == "allow" and self.returncode == 0 and not self.timed_out


def _resolve_interpreter(command) -> list[str]:
    """Replace a leading interpreter token with sys.executable so `squad check`
    works even when the venv is not activated."""
    out: list[str] = []
    for part in command:
        if part in ("python", "python3", "{python}"):
            out.append(sys.executable)
        else:
            out.append(str(part))
    return out


def run_checks(repo_config: dict, policy: Policy, cwd: str, adapter=None) -> list[CheckResult]:
    """Run every configured check command that the guard allows."""
    check_commands = (repo_config.get("repo") or {}).get("check_commands") or {}
    results: list[CheckResult] = []

    for name, tool in CHECK_TOOLS.items():
        command = check_commands.get(name)
        if not command:
            continue
        if not isinstance(command, (list, tuple)) or not all(isinstance(p, str) for p in command):
            raise ValueError(f"check_commands.{name} must be a list of strings (no shell string)")
        resolved = _resolve_interpreter(list(command))

        request = ToolRequest(tool=tool, args={}, cwd=cwd, isolation_level=0, trusted=True)
        decision = evaluate(request, policy)
        if decision.verdict is not Verdict.ALLOW:
            results.append(
                CheckResult(
                    name,
                    tool,
                    tuple(resolved),
                    decision.verdict.value,
                    None,
                    False,
                    "",
                    decision.reason,
                )
            )
            continue

        result: ProcessResult = run_command(resolved, cwd=cwd, isolation_level=0, is_agent_code=False, adapter=adapter)
        results.append(
            CheckResult(
                name,
                tool,
                tuple(resolved),
                "allow",
                result.returncode,
                result.timed_out,
                result.stdout,
                result.stderr,
            )
        )
    return results
