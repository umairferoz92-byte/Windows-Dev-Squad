"""Tests for the append-only, hash-chained audit log."""

import json

from squad.audit import AuditLog


def test_append_chain_and_verify(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"))
    e1 = log.append("run_start", agent="coder")
    e2 = log.append("tool_call", tool="edit_file")
    assert e2["prev_hash"] == e1["hash"]
    assert log.latest_hash == e2["hash"]
    assert log.verify() is True


def test_empty_log(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"))
    assert log.latest_hash == ""
    assert log.verify() is True


def test_tamper_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(str(path))
    log.append("run_start")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "tampered", "hash": "bad"}) + "\n")
    assert AuditLog(str(path)).verify() is False
