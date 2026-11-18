"""POSIX adapter (Linux/macOS): process groups + killpg.

Marked experimental: this only guarantees process-tree cleanup via process
groups; it does not provide the strong isolation of Windows Sandbox/VM.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess

from squad.exec.adapter import OSAdapter
from squad.exec.result import ProcessResult


class PosixAdapter(OSAdapter):
    name = "posix"
    platform = "linux|darwin"

    def __init__(self) -> None:
        self.shell = self._detect_shell()

    @staticmethod
    def _detect_shell() -> str | None:
        for shell in ("zsh", "bash"):
            if shutil.which(shell):
                return shell
        return None

    def run(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ProcessResult:
        proc = subprocess.Popen(
            list(cmd),
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
            return ProcessResult(proc.returncode, out or "", err or "", timed_out=False)
        except subprocess.TimeoutExpired:
            self._kill_tree(proc)
            out, err = proc.communicate()
            return ProcessResult(proc.returncode, out or "", err or "", timed_out=True)

    @staticmethod
    def _kill_tree(proc: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
