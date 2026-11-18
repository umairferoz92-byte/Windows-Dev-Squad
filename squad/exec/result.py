"""Subprocess result type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out
