"""Tests for squad.tools.external (external security-tool manager)."""

from __future__ import annotations

import pytest

from squad.tools.external import (
    TOOL_REGISTRY,
    build_install_command,
    detect,
    get_tool,
    installed,
    status_rows,
)


def test_registry_has_core_tools() -> None:
    names = {t.name for t in TOOL_REGISTRY}
    assert {"nmap", "metasploit", "sqlmap"}.issubset(names)


def test_get_tool_case_insensitive() -> None:
    assert get_tool("NMAP").name == "nmap"
    assert get_tool("nmap").display == "Nmap"


def test_get_tool_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_tool("does-not-exist")


def test_detect_returns_none_or_path() -> None:
    # Returns None if not installed, or a path string if installed.
    result = detect("nmap")
    assert result is None or isinstance(result, str)


def test_installed_shape() -> None:
    inst = installed()
    assert "nmap" in inst and "metasploit" in inst
    assert all(v is None or isinstance(v, str) for v in inst.values())


def test_status_rows_fields() -> None:
    rows = status_rows()
    assert rows, "expected at least one tool row"
    row = rows[0]
    for key in ("name", "display", "description", "installed", "path", "license", "note"):
        assert key in row, f"missing field {key}"


def test_build_install_command_returns_or_raises() -> None:
    # If a package manager is present, returns a command string containing the
    # tool name; otherwise raises RuntimeError (no manager on the box).
    try:
        cmd = build_install_command("nmap")
        assert "nmap" in cmd.lower()
    except RuntimeError:
        # acceptable on boxes with no winget/scoop/choco/apt/brew
        pass


def test_build_install_command_unknown_raises() -> None:
    with pytest.raises(KeyError):
        build_install_command("nope")
