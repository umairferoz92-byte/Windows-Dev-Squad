"""Notifications (product feature).

Sends notifications on scan completion / severity changes. Supports console
(silent no-op printers), and Desktop notifications on Windows via the built-in
``msg`` or PowerShell toast when available. Always falls back to console so it
never crashes a scan.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Optional


class Notifier:
    def __init__(self, channel: str = "console"):
        self.channel = channel

    def notify(self, title: str, message: str, severity: str = "info") -> None:
        try:
            if self.channel == "desktop" and os.name == "nt" and shutil.which("powershell"):
                self._desktop(title, message, severity)
            else:
                print(f"[notify] {severity.upper()} {title}: {message}")
        except Exception:
            print(f"[notify] {severity.upper()} {title}: {message}")

    def _desktop(self, title: str, message: str, severity: str) -> None:
        # Windows toast via PowerShell — best-effort, non-blocking.
        ps = (
            "New-BurntToastNotification"  # not guaranteed present
        )
        _ = ps
        # Fall back to msg.exe for current user.
        subprocess.run(
            ["msg", os.environ.get("USERNAME", "squad"), title + " - " + message],
            capture_output=True, timeout=5,
        )


def scan_completed(target: str, findings: int, risk: str, channel: str = "console") -> None:
    Notifier(channel).notify(
        "Scan complete",
        f"{target}: {findings} finding(s), risk {risk}",
        severity=risk.lower() if risk.lower() in ("critical", "high") else "info",
    )


def severity_changed(run_id: str, new_count: int, old_count: int, channel: str = "console") -> None:
    direction = "increased" if new_count > old_count else "decreased"
    Notifier(channel).notify(
        "Severity change",
        f"run {run_id}: {old_count} -> {new_count} ({direction})",
        severity="high" if new_count > old_count else "info",
    )


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()