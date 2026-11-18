"""Sequential crew: roster, gates, flagged files, orchestration."""

from __future__ import annotations

from squad.crew.crew import RunResult, run_sequential
from squad.crew.flagged import classify_changed_files, classify_file, flagged_files
from squad.crew.gates import GateResult, evaluate_gates, gates_all_pass
from squad.crew.parallel import run_parallel
from squad.crew.roster import HARD_MAX_AGENTS, AgentSpec, assemble_crew, estimate_run_cost
from squad.crew.worktrees import add_worktree, list_worktrees, remove_worktree

__all__ = [
    "AgentSpec",
    "HARD_MAX_AGENTS",
    "assemble_crew",
    "estimate_run_cost",
    "GateResult",
    "evaluate_gates",
    "gates_all_pass",
    "classify_file",
    "classify_changed_files",
    "flagged_files",
    "RunResult",
    "run_sequential",
    "run_parallel",
    "add_worktree",
    "list_worktrees",
    "remove_worktree",
]
