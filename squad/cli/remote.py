"""Daemon management for the remote gateway (`squad remote on|off|revoke`).

The ``on`` subcommand spawns ``squad remote serve`` as a detached background
process and records its pid in a pidfile under the squad data dir. ``off``
reads that pidfile and terminates the daemon. ``revoke`` clears the persisted
web session store. Each function is written so it can be driven
with injected collaborators (Popen, session store) for offline unit tests.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from squad.config.data import data_dir

PIDFILE_NAME = "remote.pid"


def pidfile_path() -> Path:
    """Where the remote gateway daemon records its pid."""
    return data_dir() / PIDFILE_NAME


def remote_on(host: str, port: int, popen=None, pidfile: Path | None = None) -> tuple[int, str]:
    """Spawn the remote gateway as a detached daemon; return (pid, url).

    On Windows the process is created with DETACHED_PROCESS and
    CREATE_NEW_PROCESS_GROUP; on POSIX with a new session. The daemon's pid is
    written to the pidfile so ``off`` can find and terminate it later.
    """
    popen = popen or subprocess.Popen
    cmd = [
        sys.executable,
        "-m",
        "squad",
        "remote",
        "serve",
        "--host",
        host,
        "--port",
        str(port),
    ]
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True

    proc = popen(cmd, **kwargs)
    path = pidfile or pidfile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(proc.pid), encoding="utf-8")
    return proc.pid, f"http://{host}:{port}"


def remote_off(pidfile: Path | None = None) -> int | None:
    """Terminate the daemon recorded in the pidfile and remove the pidfile.

    Returns the terminated pid, or ``None`` if no pidfile (or no usable pid)
    was found.
    """
    path = pidfile or pidfile_path()
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid = None
    if pid is not None:
        _terminate(pid)
    try:
        path.unlink()
    except OSError:
        pass
    return pid


def _terminate(pid: int) -> None:
    """Terminate a process, killing its tree on Windows (taskkill /T /F)."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        except OSError:
            pass
    else:
        try:
            os.kill(pid, 15)  # SIGTERM
        except OSError:
            pass


def remote_revoke(sessions) -> int:
    """Clear all persisted web sessions; return how many were active."""
    count = getattr(sessions, "count", lambda: 0)()
    revoke_all = getattr(sessions, "revoke_all", None)
    if revoke_all is not None:
        revoke_all()
    return int(count)
