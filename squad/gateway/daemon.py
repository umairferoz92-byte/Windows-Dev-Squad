"""Background daemon lifecycle for ``squad remote on|off|revoke``.

Manages a persistent pidfile under the squad data dir so the ``remote``
subcommands can start, stop cached, and revoke the gateway across processes.
"""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from squad.config.data import data_dir

PIDFILE_NAME = "remote.pid"


def _pidfile() -> Path:
    return data_dir() / PIDFILE_NAME


def daemon_running() -> bool:
    """True if a pidfile exists and that pid is still alive."""
    path = _pidfile()
    if not path.exists():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if os.name == "nt":
        # Windows: a pid is alive if it exists; kill(pid,0) semantics via OpenProcess.
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_daemon(port: int = 8765) -> str:
    """Launch ``squad remote serve`` in a detached background process.

    Returns the URL the daemon is serving on.
    """
    from squad.cli.app import _venv_squad_exe

    exe = _venv_squad_exe()
    flags = (
        subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        if os.name == "nt"
        else getattr(subprocess, "START_NEW_SESSION", 0)
    )
    proc = subprocess.Popen(
        [exe, "remote", "serve", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        start_new_session=os.name != "nt",
    )
    data_dir().mkdir(parents=True, exist_ok=True)
    _pidfile().write_text(str(proc.pid), encoding="utf-8")
    return f"http://127.0.0.1:{port}"


def stop_daemon() -> bool:
    """Terminate the daemon recorded in the pidfile; remove the pidfile."""
    path = _pidfile()
    stopped = False
    if path.exists():
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = None
        if pid is not None and daemon_running():
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    os.kill(pid, signal.SIGTERM)
                stopped = True
            except (OSError, subprocess.SubprocessError):
                stopped = False
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return stopped


def revoke_sessions() -> None:
    """Clear any persisted session store so new logins issue fresh sessions."""
    # Session tokens are short-lived and held in memory by the running daemon;
    # forcing a new login means stopping+restarting the daemon. Here we stop it.
    stop_daemon()
