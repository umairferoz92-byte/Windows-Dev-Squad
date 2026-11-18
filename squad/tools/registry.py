"""The typed-tool registry (name -> ToolSpec), derived from the guard's tool tiers."""

from __future__ import annotations

from squad.guard.policy import DEFAULT_POLICY
from squad.tools.spec import ToolSpec

_DESCRIPTIONS: dict[str, str] = {
    "read_file": "Read a file from the repo.",
    "search_code": "Search the repo for a pattern.",
    "repo_map": "Produce a structural map of the repo.",
    "git_diff": "Show uncommitted changes.",
    "git_status": "Show the working-tree status.",
    "run_security_scan": "Run the fixed security-scan commands from squad.yaml.",
    "run_tests": "Run the configured test command.",
    "run_lint": "Run the configured linter.",
    "run_typecheck": "Run the configured type checker.",
    "edit_file": "Edit a file within the configured write scope.",
    "git_commit": "Commit on the agent's own branch.",
    "install_dependencies": "Install a dependency (Tier 2, always asks).",
    "git_push": "Push a branch (blocked).",
    "raw_shell": "Run a raw shell command (blocked).",
    "credential_access": "Access credentials (blocked).",
    "invoke_squad": "Invoke the squad CLI (blocked).",
    "admin_elevation": "Elevate to administrator (blocked).",
}


def _build_registry() -> dict[str, ToolSpec]:
    registry: dict[str, ToolSpec] = {}
    for name, entry in DEFAULT_POLICY["tools"].items():
        registry[name] = ToolSpec(
            name=name,
            tier=entry.get("tier", 2),
            description=_DESCRIPTIONS.get(name, ""),
        )
    return registry


TOOLS: dict[str, ToolSpec] = _build_registry()


def get_tool(name: str) -> ToolSpec | None:
    return TOOLS.get(name)


def tier_of(name: str) -> int | None:
    tool = TOOLS.get(name)
    return tool.tier if tool is not None else None
