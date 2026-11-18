"""OS-adapter interface: everything OS-specific lives behind this.

Windows Job Objects (``squad/exec/windows``) and POSIX process groups
(``squad/exec/posix.py``) are concrete adapters. The guard, budget layer, agents
and reports never import OS specifics directly.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from squad.exec.result import ProcessResult


class OSAdapter(ABC):
    name: str = "base"
    platform: str = "unknown"

    @abstractmethod
    def run(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ProcessResult:
        """Run ``cmd`` as an argument list and capture UTF-8 output.

        Implementations must guarantee no orphaned process tree remains when
        this returns (including on timeout), and must never use a shell.
        """
        raise NotImplementedError

    def supports_isolation(self, level: int) -> bool:
        """True if agent code can actually run at this isolation level."""
        return level == 0


def get_adapter() -> OSAdapter:
    """Return the adapter for the current platform."""
    if os.name == "nt":
        from squad.exec.windows.adapter import WindowsAdapter

        return WindowsAdapter()
    from squad.exec.posix import PosixAdapter

    return PosixAdapter()
