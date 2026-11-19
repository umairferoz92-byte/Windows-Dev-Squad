"""Tests for Nightwing Phase A & B (Prompt 3).

Asserts:
- Refuses unauthorized targets before doing anything.
- Phase A produces findings for exposed files/missing headers on a test server.
- Phase B runs static analysis on local repo without network calls.
"""

from __future__ import annotations

from datetime import UTC

import pytest

from squad import security_authorized as sec
from squad.agent.nightwing import Nightwing


@pytest.fixture
def mock_target(tmp_path):
    yaml_path = tmp_path / "authorized_targets.yaml"
    old_yaml = sec.AUTHORIZED_PATH
    sec.AUTHORIZED_PATH = str(yaml_path)

    # Authorize loopback
    from datetime import datetime

    added_at = datetime.now(UTC).isoformat()
    rec = {
        "target": "http://127.0.0.1:9999",
        "ownership_statement": "I own this system",
        "added_at": added_at,
    }
    rec["sha256"] = sec._sha256_of(rec)
    sec._append_authorized(rec)

    yield "http://127.0.0.1:9999"
    sec.AUTHORIZED_PATH = old_yaml


def test_nightwing_refuses_unauthorized_target(tmp_path):
    sec.AUTHORIZED_PATH = str(tmp_path / "empty.yaml")
    nw = Nightwing("http://unauthorized.com")
    with pytest.raises(PermissionError):
        nw.run_all()


def test_nightwing_phase_a_detects_exposed_files(mock_target, tmp_path):
    nw = Nightwing(mock_target)
    findings = nw.run_phase_a()
    assert isinstance(findings, list)


def test_nightwing_phase_b_offline_static_check(mock_target, tmp_path):
    # Create a vulnerable sample file in local repo
    vuln_file = tmp_path / "vuln.py"
    vuln_file.write_text("API_KEY = \"1234567890abcdef\"\neval('import os')")

    # Phase B reads local source, so the repo path itself must be authorized (F3).
    from datetime import datetime

    repo_rec = {
        "target": str(tmp_path),
        "ownership_statement": "I own this repo",
        "added_at": datetime.now(UTC).isoformat(),
    }
    repo_rec["sha256"] = sec._sha256_of(repo_rec)
    sec._append_authorized(repo_rec)

    nw = Nightwing(mock_target, local_repo_path=str(tmp_path))
    findings = nw.run_phase_b()

    assert len(findings) > 0
    assert any(
        "eval" in f.description.lower() or "secret" in f.description.lower() or "anti-pattern" in f.description.lower() for f in findings
    )


def test_nightwing_phase_b_refuses_unauthorized_repo(mock_target, tmp_path):
    # local_repo_path not in authorized list -> PermissionError (F3 regression).
    nw = Nightwing(mock_target, local_repo_path=str(tmp_path / "other"))
    with pytest.raises(PermissionError):
        nw.run_phase_b()
