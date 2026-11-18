"""Guard — a default-deny policy decision layer. NOT a sandbox.

The guard approves or denies *requests* and checks *arguments*; it does not
contain processes. Agent code runs inside the configured isolation level. See
docs/RULES.md (rule 1).
"""

from __future__ import annotations

from squad.guard.approvals import Approval, ApprovalStore
from squad.guard.decide import ToolRequest, evaluate
from squad.guard.paths import PathError, canonical, is_blocked, is_within
from squad.guard.patterns import has_destructive
from squad.guard.policy import DEFAULT_POLICY, Policy
from squad.guard.verdict import Decision, Verdict

__all__ = [
    "Verdict",
    "Decision",
    "ToolRequest",
    "Approval",
    "ApprovalStore",
    "Policy",
    "DEFAULT_POLICY",
    "PathError",
    "evaluate",
    "canonical",
    "is_within",
    "is_blocked",
    "has_destructive",
]
