"""The guard's default-deny decision engine."""

from __future__ import annotations

import os
from dataclasses import dataclass

from squad.guard.paths import canonical, fold_component, is_blocked, is_within, path_components
from squad.guard.patterns import has_destructive
from squad.guard.policy import Policy
from squad.guard.verdict import Decision, Verdict

_COMMAND_ARG_KEYS = ("command", "cmd", "shell", "script", "args", "argv")


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    args: dict
    cwd: str
    isolation_level: int | None = None
    actor: str = "agent"
    trusted: bool = False


def evaluate(request, policy=None, approvals=None) -> Decision:
    """Decide ALLOW / ASK / DENY for one tool request.

    ``policy`` may be a :class:`Policy` or a plain dict; ``approvals`` is
    reserved for the terminal approval flow (Phase 5) and is accepted here for
    API stability only.
    """
    p = policy if isinstance(policy, Policy) else Policy(policy)
    data = p.data

    entry = data.get("tools", {}).get(request.tool)
    if entry is None:
        if data.get("default_deny", True) is False:
            return Decision(Verdict.ALLOW, f"unknown tool '{request.tool}' allowed by default_deny=False")
        return Decision(Verdict.ASK, f"unknown tool '{request.tool}' (default deny)")

    if _has_destructive_args(request.args):
        return Decision(Verdict.DENY, "destructive command pattern detected in arguments")

    tier = _effective_tier(entry, request)

    if tier == 3:
        return Decision(Verdict.DENY, f"tool '{request.tool}' is blocked (tier 3)")
    if tier == 2:
        return Decision(Verdict.ASK, f"tool '{request.tool}' requires approval (tier 2)")
    if tier == 0:
        return Decision(Verdict.ALLOW, f"tool '{request.tool}' allowed (tier 0)")
    if tier == 1:
        return _evaluate_tier1(request, data)
    return Decision(Verdict.DENY, f"tool '{request.tool}' has an invalid tier")


def _effective_tier(entry: dict, request) -> int:
    base = entry.get("tier", 2)
    required = entry.get("requires_isolation_level")
    if required is not None and base == 0 and not request.trusted:
        level = request.isolation_level
        if level is None or level < required:
            return 2
    return base


def _has_destructive_args(args: dict) -> bool:
    for key, value in args.items():
        if key in _COMMAND_ARG_KEYS and isinstance(value, str):
            if has_destructive(value):
                return True
    return False


def _evaluate_tier1(request, data: dict) -> Decision:
    if request.tool == "edit_file":
        return _evaluate_edit_file(request, data)
    return Decision(Verdict.ALLOW, f"tool '{request.tool}' allowed (tier 1)")


def _evaluate_edit_file(request, data: dict) -> Decision:
    path = request.args.get("path")
    if not isinstance(path, str) or not path:
        return Decision(Verdict.DENY, "edit_file requires a non-empty 'path' argument")

    if is_blocked(path, data):
        return Decision(Verdict.DENY, f"'{path}' is a blocked path")
    if _is_sensitive_file(path, data):
        return Decision(Verdict.DENY, f"'{path}' is a sensitive file (config)")
    if _is_sensitive_dir(path, data):
        return Decision(Verdict.ASK, f"'{path}' is under a sensitive directory (needs approval)")

    if not is_within(path, data.get("write_scope", [])):
        return Decision(Verdict.ASK, f"'{path}' is outside the configured write scope")
    return Decision(Verdict.ALLOW, f"edit_file '{path}' is within scope and safe")


def _is_sensitive_file(path: str, data: dict) -> bool:
    target = canonical(path)
    sensitive = {fold_component(f) for f in data.get("sensitive_files", [])}
    return fold_component(os.path.basename(target)) in sensitive


def _is_sensitive_dir(path: str, data: dict) -> bool:
    target = canonical(path)
    sensitive = {fold_component(d) for d in data.get("sensitive_dirs", [])}
    return any(fold_component(c) in sensitive for c in path_components(target))
