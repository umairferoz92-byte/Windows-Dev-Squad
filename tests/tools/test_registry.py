"""Tests for the typed-tool registry."""

from squad.tools import TOOLS, get_tool, tier_of


def test_registry_tiers():
    assert tier_of("read_file") == 0
    assert tier_of("edit_file") == 1
    assert tier_of("install_dependencies") == 2
    assert tier_of("git_push") == 3


def test_registry_covers_all_guard_tools():
    from squad.guard.policy import DEFAULT_POLICY

    assert set(TOOLS) == set(DEFAULT_POLICY["tools"])


def test_unknown_tool_returns_none():
    assert get_tool("does_not_exist") is None
    assert tier_of("does_not_exist") is None
