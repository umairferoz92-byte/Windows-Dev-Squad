"""AuditLog self-heals from truncated/partial trailing writes."""

from __future__ import annotations

import json

from squad.audit.audit import AuditLog


def test_append_survives_truncated_tail_line(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(str(path))
    log.append("a")
    log.append("b")
    # Simulate an interrupted write: a valid-JSON but incomplete dict with no hash
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "partial", "timestamp": 1.0}) + "\n")
    # Re-open: must not crash on the partial line
    log2 = AuditLog(str(path))
    log2.append("c")
    # Only fully-chained entries survive loading
    assert len(log2._entries) == 3
    assert [e["event"] for e in log2._entries] == ["a", "b", "c"]
    # The intact chain still verifies
    assert log2.verify()


def test_load_drops_truly_bad_line(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        fh.write("not-json-at-all\n")
    log = AuditLog(str(path))
    assert log._entries == []
    log.append("ok")
    assert log.verify()
