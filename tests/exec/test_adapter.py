"""Tests for the OS adapters, including the "no orphaned processes" guarantee."""

import os
import sys
import time

from squad.exec import get_adapter


def _is_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
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


def test_get_adapter_matches_platform():
    adapter = get_adapter()
    if os.name == "nt":
        assert adapter.name == "windows"
    else:
        assert adapter.name == "posix"


def test_run_captures_output():
    adapter = get_adapter()
    result = adapter.run([sys.executable, "-c", "print('hello from adapter')"])
    assert result.returncode == 0
    assert "hello from adapter" in result.stdout


def test_run_reports_timeout():
    adapter = get_adapter()
    result = adapter.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
    assert result.timed_out is True


def test_run_kills_process_tree_on_timeout(tmp_path):
    """A timed-out command must not leave its children (grandchildren) behind."""
    adapter = get_adapter()
    pidfile = tmp_path / "grandchild.pid"
    grandchild = (
        f"import os, time; open({str(pidfile)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); "
        "time.sleep(60)"
    )
    result = adapter.run([sys.executable, "-c", parent], timeout=2)
    assert result.timed_out is True

    time.sleep(0.5)
    assert pidfile.exists()
    grandchild_pid = int(pidfile.read_text())
    assert _is_alive(grandchild_pid) is False
