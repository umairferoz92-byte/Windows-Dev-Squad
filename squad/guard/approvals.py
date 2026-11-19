"""Human-only, bound, expiring approvals (rule 2).

Approvals come only from the human, are bound to the exact command and working
directory, and expire after a fixed TTL (default 5 minutes). Agents can never
grant approvals.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from squad.guard.paths import canonical

HUMAN = "human"
DEFAULT_TTL_SECONDS = 300


@dataclass(frozen=True)
class Approval:
    id: str
    approver: str
    command: str
    cwd: str
    args: dict
    created_at: float
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    def is_expired(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return now - self.created_at > self.ttl_seconds


_PATH_ARG_KEYS = ("path", "file", "target", "dir", "source", "dest", "destination")


def _canonical_arg(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_canonical_arg(v) for v in value)
    if isinstance(value, dict):
        return _canonical_args(value)
    return value


def _canonical_args(args: dict) -> tuple:
    out = []
    for key in sorted(args):
        value = args[key]
        if isinstance(value, str) and key in _PATH_ARG_KEYS:
            value = canonical(value)
        else:
            value = _canonical_arg(value)
        out.append((key, value))
    return tuple(out)


class ApprovalStore:
    def __init__(self) -> None:
        self._items: dict[str, Approval] = {}

    def grant(self, approver: str, command: str, cwd: str, args: dict, ttl_seconds: int = 300) -> Approval:
        if approver != HUMAN:
            raise ValueError("only the human can grant approvals")
        approval = Approval(
            id=uuid.uuid4().hex,
            approver=HUMAN,
            command=command,
            cwd=canonical(cwd),
            args=dict(args),
            created_at=time.time(),
            ttl_seconds=ttl_seconds,
        )
        self._items[approval.id] = approval
        return approval

    def lookup(self, approval_id: str) -> Approval | None:
        return self._items.get(approval_id)

    def find_valid(self, command: str, cwd: str, args: dict, now: float | None = None) -> Approval | None:
        now = time.time() if now is None else now
        target_cwd = canonical(cwd)
        target_args = _canonical_args(args)
        for approval in self._items.values():
            if approval.is_expired(now):
                continue
            if approval.command != command:
                continue
            if canonical(approval.cwd) != target_cwd:
                continue
            if _canonical_args(approval.args) != target_args:
                continue
            return approval
        return None
