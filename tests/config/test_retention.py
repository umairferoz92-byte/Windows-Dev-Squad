"""Tests for retention (age-based archiving)."""

from squad.config import partition_by_age


def test_partition_by_age():
    now = 100000.0
    entries = [
        {"timestamp": 9000.0, "e": "old"},
        {"timestamp": 20000.0, "e": "keep"},
    ]
    keep, archived = partition_by_age(entries, max_age_days=1, now=now)
    assert [e["e"] for e in keep] == ["keep"]
    assert [e["e"] for e in archived] == ["old"]
