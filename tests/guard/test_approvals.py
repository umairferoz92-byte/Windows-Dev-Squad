"""Tests for human-only, bound, expiring approvals (rule 2)."""

import pytest

from squad.guard import ApprovalStore


def test_grant_and_lookup():
    store = ApprovalStore()
    approval = store.grant("human", "edit_file", "/repo", {"path": "/repo/src/a.py"})
    assert store.lookup(approval.id) == approval


def test_agent_cannot_approve():
    store = ApprovalStore()
    with pytest.raises(ValueError):
        store.grant("agent", "edit_file", "/repo", {"path": "/repo/src/a.py"})


def test_valid_within_ttl():
    store = ApprovalStore()
    approval = store.grant("human", "edit_file", "/repo", {"path": "/repo/src/a.py"})
    found = store.find_valid(
        "edit_file", "/repo", {"path": "/repo/src/a.py"}, now=approval.created_at + 1
    )
    assert found is not None


def test_expired_rejected():
    store = ApprovalStore()
    approval = store.grant(
        "human", "edit_file", "/repo", {"path": "/repo/src/a.py"}, ttl_seconds=300
    )
    found = store.find_valid(
        "edit_file", "/repo", {"path": "/repo/src/a.py"}, now=approval.created_at + 301
    )
    assert found is None


def test_wrong_command_rejected():
    store = ApprovalStore()
    approval = store.grant("human", "edit_file", "/repo", {"path": "/repo/src/a.py"})
    found = store.find_valid(
        "git_commit", "/repo", {"path": "/repo/src/a.py"}, now=approval.created_at + 1
    )
    assert found is None


def test_wrong_cwd_rejected():
    store = ApprovalStore()
    approval = store.grant("human", "edit_file", "/repo", {"path": "/repo/src/a.py"})
    found = store.find_valid(
        "edit_file", "/other", {"path": "/repo/src/a.py"}, now=approval.created_at + 1
    )
    assert found is None


def test_wrong_args_rejected():
    store = ApprovalStore()
    approval = store.grant("human", "edit_file", "/repo", {"path": "/repo/src/a.py"})
    found = store.find_valid(
        "edit_file", "/repo", {"path": "/repo/src/b.py"}, now=approval.created_at + 1
    )
    assert found is None


def test_missing_id_lookup_returns_none():
    store = ApprovalStore()
    assert store.lookup("does-not-exist") is None
