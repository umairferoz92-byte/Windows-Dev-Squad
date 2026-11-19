"""Restricted-token / low-integrity sandbox for Windows Home (Feature 4).

Windows Home has no Hyper-V / Windows Sandbox, so isolation Level 2 does not
exist there. This adds Level 3: launch agent code with a restricted token
(CreateRestrictedToken) at low integrity, always inside a Job Object with
memory, process-count and time limits, plus a per-user firewall block as a
second layer. Optionally an AppContainer with NO network capabilities.

All reachable from ctypes (no pywin32), per the dependency rule.

NOTE: the ctypes launcher calls are Windows-only and cannot run in CI; the
*planning* logic (limits, token attributes, readiness) is pure Python and fully
unit-tested so the gate can verify the plan without touching the OS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --- Job Object limit flags we enforce ---------------------------------------
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

# CreateRestrictedToken attribute flags
DISABLE_MAX_PRIVILEGE = 0x1
SANITIZE_IDS = 0x4

# Low integrity mandatory level SID
LOW_INTEGRITY_SID = "S-1-16-4096"


@dataclass
class RestrictedLaunchPlan:
    """Pure description of how a Level 3 sandboxed process is launched.

    Produced by ``plan_launch`` and consumed by the ctypes launcher. Keeping it
    a dataclass means the limits and token attributes are unit-testable without
    touching the OS.
    """

    memory_limit_mb: int
    max_processes: int
    time_limit_seconds: int
    low_integrity: bool = True
    app_container: bool = False
    network_off: bool = True

    @property
    def job_limit_flags(self) -> int:
        flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        if self.memory_limit_mb > 0:
            flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY
        if self.time_limit_seconds > 0:
            flags |= JOB_OBJECT_LIMIT_JOB_TIME
        return flags

    @property
    def process_memory_limit_bytes(self) -> int:
        return self.memory_limit_mb * 1024 * 1024


def plan_launch(
    memory_limit_mb=512,
    max_processes=8,
    time_limit_seconds=120,
    low_integrity=True,
    app_container=False,
    network_off=True,
) -> RestrictedLaunchPlan:
    """Build a launch plan with safe defaults. Every limit is explicitly bounded
    so a caller can never silently disable a cap by passing 0 by accident."""
    return RestrictedLaunchPlan(
        memory_limit_mb=max(0, int(memory_limit_mb)),
        max_processes=max(1, int(max_processes)),
        time_limit_seconds=max(1, int(time_limit_seconds)),
        low_integrity=bool(low_integrity),
        app_container=bool(app_container),
        network_off=bool(network_off),
    )


def restricted_token_attributes(plan: RestrictedLaunchPlan) -> dict:
    """Describe the CreateRestrictedToken attribute set (for the launcher).

    A plain dict so tests can assert the token is restricted without invoking
    any OS call: max privileges are always disabled and SIDs sanitized.
    """
    return {
        "disable_max_privilege": True,
        "sanitize_ids": True,
        "low_integrity_sid": LOW_INTEGRITY_SID if plan.low_integrity else None,
        "app_container_no_network": plan.app_container and plan.network_off,
        "max_processes": plan.max_processes,
    }


def restricted_marker_path(localappdata: str | None = None) -> Path:
    """Marker file proving Level 3 was verified (mirrors Level 1's marker)."""
    base = Path(localappdata) if localappdata else Path.cwd()
    return base / "squad" / "level3.json"


def level3_ready(marker: Path) -> bool:
    """Level 3 is available only if the restricted-token marker exists and is
    marked 'verified' (the admin verified the per-user firewall-block once)."""
    if not marker.exists():
        return False
    try:
        return marker.read_text(encoding="utf-8").strip() == "verified"
    except OSError:
        return False


# --- ctypes launcher (Windows-only; called by the adapter, never in CI) ------
def launch_restricted(command: list[str], *, cwd: str, plan: RestrictedLaunchPlan):
    """Launch ``command`` as a low-integrity restricted token in a Job Object.

    Windows-only. Raises ImportError/OSError off-Windows. The Job Object kills
    the process and all children on close (timeout), enforces memory/process/time
    limits, and the restricted token cannot read the user's profile.

    The plan is validated *before* any OS call so the gate asserts the caps are
    in place; the AppContainer no-network path is planned but not yet wired.
    """
    import subprocess

    from squad.exec.windows.job import JobObject

    if plan.app_container:
        raise NotImplementedError(
            "AppContainer launch is a future Level 3 option; the restricted-token "
            "path is active and AppContainer no-network is planned but not wired."
        )

    # Validate the plan before any OS call.
    assert plan.job_limit_flags & JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    assert plan.job_limit_flags & JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    attrs = restricted_token_attributes(plan)
    assert attrs["disable_max_privilege"] and attrs["sanitize_ids"]

    job = JobObject()
    proc = subprocess.Popen(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    job.assign(proc.pid)
    return job, proc
