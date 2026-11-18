"""Tests for the Security Guard: authorized-targets management (Prompt 1).

Asserts the three core guarantees from the blueprint:
- An unauthorized target is always refused.
- A tampered authorized_targets.yaml (bad hash) is refused.
- Adding a target requires both prompts to be answered correctly.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timezone

import pytest

from squad import security_authorized as sec


@pytest.fixture
def isolated_paths(tmp_path):
    """Point the module at a temp YAML + audit log so tests never touch real data."""
    yaml_path = tmp_path / "authorized_targets.yaml"
    audit_path = tmp_path / "audit.jsonl"
    old_yaml = sec.AUTHORIZED_PATH
    old_audit = sec.AUDIT_PATH
    sec.AUTHORIZED_PATH = str(yaml_path)
    sec.AUDIT_PATH = str(audit_path)
    yield {"yaml": str(yaml_path), "audit": str(audit_path)}
    sec.AUTHORIZED_PATH = old_yaml
    sec.AUDIT_PATH = old_audit


def _make_record(target, ownership, added_at=None):
    """Build a valid, correctly-hashed record for a target."""
    added_at = added_at or datetime.now(timezone.utc).isoformat()
    rec = {"target": target, "ownership_statement": ownership, "added_at": added_at}
    rec["sha256"] = sec._sha256_of(rec)
    return rec


def _write_yaml(path, records):
    import yaml
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(records, f, default_flow_style=False, sort_keys=True)


def test_unauthorized_target_always_refused(isolated_paths):
    """No records -> every target is refused."""
    assert sec.is_authorized("http://example.com") is False
    assert sec.is_authorized("http://127.0.0.1:8765") is False
    assert sec.is_authorized("") is False
    assert sec.is_authorized(None) is False


def test_added_target_is_authorized(isolated_paths):
    """Once a target is added (with correct hash), it becomes authorized."""
    rec = _make_record("http://127.0.0.1:8765", "I own this system")
    sec._append_authorized(rec)
    assert sec.is_authorized("http://127.0.0.1:8765") is True


def test_tampered_record_is_refused(isolated_paths):
    """A record whose sha256 does not match its fields must be refused.

    The blueprint: "a tampered authorized_targets.yaml (bad hash) is refused".
    """
    # Add a valid record, then corrupt the ownership statement without updating the hash
    rec = _make_record("http://127.0.0.1:8765", "I own this system")
    sec._append_authorized(rec)

    # Now tamper: change the stored record's ownership in the YAML but keep old sha256
    import yaml
    with open(isolated_paths["yaml"], "r", encoding="utf-8") as f:
        records = yaml.safe_load(f) or []
    assert records, "expected at least one record"
    records[0]["ownership_statement"] = "MALLICIOUS OVERRIDE - not the owner"
    with open(isolated_paths["yaml"], "w", encoding="utf-8") as f:
        yaml.dump(records, f, default_flow_style=False, sort_keys=True)

    # _load_authorized drops records whose hash no longer matches -> target unauthorized
    assert sec.is_authorized("http://127.0.0.1:8765") is False


def test_add_target_requires_both_prompts(isolated_paths, monkeypatch, capsys):
    """Adding a target requires the ownership statement AND the exact target string.

    If the user types a different string on the second prompt, the record is
    NOT added and is_authorized stays False.
    """
    # Simulate mismatch: first target = 127.0.0.1, confirmation = different
    answers = iter(["I own this system", "http://127.0.0.1:8765", "http://WRONG.example"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    sec.cmd_security_add_target()

    out = capsys.readouterr().out
    assert "did not match" in out
    assert "authorized target added" not in out
    assert sec.is_authorized("http://127.0.0.1:8765") is False


def test_add_target_writes_record_and_audit(isolated_paths, monkeypatch, capsys):
    """With correct input, the record is written and the audit log is appended."""
    answers = iter(["I own this system", "http://127.0.0.1:8765", "http://127.0.0.1:8765"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    sec.cmd_security_add_target()

    out = capsys.readouterr().out
    assert "authorized target added" in out
    assert sec.is_authorized("http://127.0.0.1:8765") is True

    # Audit log has the add event and its chain verifies
    from squad.audit.audit import AuditLog
    log = AuditLog(isolated_paths["audit"])
    assert log.verify()
    events = [e.get("event") for e in log._entries]
    assert "authorized_targets.add" in events
