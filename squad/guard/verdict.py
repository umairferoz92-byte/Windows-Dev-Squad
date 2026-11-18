"""Guard decision verdicts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW
