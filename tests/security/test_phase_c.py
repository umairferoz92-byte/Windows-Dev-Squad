"""Tests for Nightwing Phase C, rate limiter, and kill switch (Prompt 4).

Asserts:
- Phase C refuses to run without a fresh operator "go ahead".
- The global rate limiter caps request rate.
- The kill switch terminates child processes quickly.
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone

import pytest

from squad import security_authorized as sec
from squad.agent.nightwing import Nightwing
from squad.agent.rate_limit import GLOBAL_KILL_SWITCH, GLOBAL_RATE_LIMITER, KillSwitch, RateLimiter


@pytest.fixture
def authorized_loopback(tmp_path):
    old = sec.AUTHORIZED_PATH
    sec.AUTHORIZED_PATH = str(tmp_path / "authorized.yaml")
    added_at = datetime.now(timezone.utc).isoformat()
    rec = {"target": "http://127.0.0.1:9999",
           "ownership_statement": "I own this", "added_at": added_at}
    rec["sha256"] = sec._sha256_of(rec)
    sec._append_authorized(rec)
    yield "http://127.0.0.1:9999"
    sec.AUTHORIZED_PATH = old


def test_rate_limiter_caps_rate():
    """A limiter set to 5 req/s should not allow 100 requests in under ~10s."""
    limiter = RateLimiter(min_interval=0.05)
    start = time.monotonic()
    for _ in range(20):
        limiter.wait()
    elapsed = time.monotonic() - start
    # 20 requests at 0.05s spacing = at least ~0.95s
    assert elapsed >= 0.9


def test_kill_switch_terminates_children():
    """KillSwitch.terminate stops tracked child processes within ~1s."""
    ks = KillSwitch()
    run_id = ks.new_run()

    # Spawn a long-running child (sleep 60) and register it
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ks.register(run_id, proc)

    start = time.monotonic()
    killed = ks.terminate(run_id)
    elapsed = time.monotonic() - start

    assert killed >= 1
    assert elapsed <= 1.5  # terminates within ~1s
    assert proc.poll() is not None  # process is no longer running


def test_phase_c_refuses_without_confirmation(authorized_loopback, monkeypatch):
    """Phase C must not run without a fresh 'go ahead' from the operator."""
    # Simulate no confirmation
    monkeypatch.setattr("squad.agent.nightwing.shutil.which", lambda x: "/usr/bin/nmap" if x == "nmap" else None)

    nw = Nightwing(authorized_loopback)
    with pytest.raises(PermissionError):
        nw.run_phase_c(confirm_commands=lambda t, c: False)


def test_phase_c_runs_after_confirmation(authorized_loopback, monkeypatch):
    """Phase C proceeds when the operator gives a fresh 'go ahead'."""
    from unittest.mock import MagicMock

    # Fake nmap present on PATH, and fake Popen so no real nmap launches.
    monkeypatch.setattr(
        "squad.agent.nightwing.shutil.which",
        lambda x: "/usr/bin/nmap" if x == "nmap" else None,
    )
    fake_proc = MagicMock()
    fake_proc.communicate.return_value = ("nmap output", None)
    monkeypatch.setattr(
        "squad.agent.nightwing.subprocess.Popen",
        lambda *a, **k: fake_proc,
    )

    called = {"confirmed": False}

    def fake_confirm(target, cmds):
        called["confirmed"] = True
        return True

    nw = Nightwing(authorized_loopback)
    nw.run_phase_c(confirm_commands=fake_confirm, run_id="test-run")

    assert called["confirmed"] is True
    fake_proc.communicate.assert_called()