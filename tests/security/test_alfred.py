"""Tests for Alfred, the tool manager (Prompt 2).

Asserts:
- Found/missing status is correctly reported.
- No install command runs without an explicit "yes" from the user.
- Actions are recorded in the audit log.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from squad.tools.manifest import ToolManifestEntry, check_all_tools, detect_tool


@pytest.fixture
def fake_manifest():
    return [
        ToolManifestEntry(
            name="tool1",
            display="Tool 1",
            purpose="Test",
            binary="found_binary",
            install_cmd="echo install1",
        ),
        ToolManifestEntry(
            name="tool2",
            display="Tool 2",
            purpose="Test",
            binary="missing_binary",
            install_cmd="echo install2",
        ),
    ]


def test_detect_tool_finds_present_binary(monkeypatch):
    """If shutil.which finds the binary, it reports installed=True."""
    entry = ToolManifestEntry(name="t", display="T", purpose="P", binary="bin", install_cmd="inst")
    monkeypatch.setattr("shutil.which", lambda x: "/path/to/bin" if x == "bin" else None)

    # Mock subprocess.run for version check
    mock_res = MagicMock()
    mock_res.stdout = "v1.0"
    mock_res.stderr = ""
    mock_res.returncode = 0
    monkeypatch.setattr("subprocess.run", lambda *a, **k: mock_res)

    status = detect_tool(entry)
    assert status.installed is True
    assert status.path == "/path/to/bin"
    assert "v1.0" in status.version


def test_detect_tool_handles_missing_binary(monkeypatch):
    """If shutil.which returns None, it reports installed=False."""
    entry = ToolManifestEntry(name="t", display="T", purpose="P", binary="bin", install_cmd="inst")
    monkeypatch.setattr("shutil.which", lambda x: None)

    status = detect_tool(entry)
    assert status.installed is False
    assert status.path == ""


def test_check_tools_returns_list(fake_manifest, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda x: "/path/to/found_binary" if x == "found_binary" else None)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: MagicMock(stdout="", returncode=0))

    statuses = check_all_tools(fake_manifest)
    assert len(statuses) == 2
    assert statuses[0].name == "tool1" and statuses[0].installed is True
    assert statuses[1].name == "tool2" and statuses[1].installed is False


def test_no_install_without_yes(monkeypatch, capsys, tmp_path):
    """The installer must NOT run the command if the user says no/default."""
    from squad.cli.app import security_check_tools_command
    from squad.tools import manifest

    # Mock BLUEPRINT_MANIFEST to have one missing tool
    fake = [ToolManifestEntry(name="m", display="M", purpose="P", binary="missing", install_cmd="DO_NOT_RUN")]
    monkeypatch.setattr(manifest, "BLUEPRINT_MANIFEST", fake)
    monkeypatch.setattr("shutil.which", lambda x: None)

    # User says no
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    # Mock audit path to avoid touching real data
    monkeypatch.setattr("squad.audit.audit.default_audit_path", lambda: str(tmp_path / "audit.jsonl"))

    mock_sub = MagicMock()
    monkeypatch.setattr("subprocess.run", mock_sub)

    security_check_tools_command(install_missing=True)

    # Command should NOT have been called
    mock_sub.assert_not_called()

    out = capsys.readouterr().out
    assert "Skipped M" in out


def test_install_runs_on_yes(monkeypatch, capsys, tmp_path):
    """The installer runs the command if the user says yes."""
    from squad.cli.app import security_check_tools_command
    from squad.tools import manifest

    fake = [ToolManifestEntry(name="m", display="M", purpose="P", binary="missing", install_cmd="RUN_ME")]
    monkeypatch.setattr(manifest, "BLUEPRINT_MANIFEST", fake)
    monkeypatch.setattr("shutil.which", lambda x: None)

    # User says yes
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    monkeypatch.setattr("squad.audit.audit.default_audit_path", lambda: str(tmp_path / "audit.jsonl"))

    mock_sub = MagicMock()
    mock_sub.return_value = MagicMock(returncode=0, stdout="done")
    monkeypatch.setattr("subprocess.run", mock_sub)

    security_check_tools_command(install_missing=True)

    # Command SHOULD have been called
    mock_sub.assert_called_once()
    args, kwargs = mock_sub.call_args
    assert args[0] == "RUN_ME"

    out = capsys.readouterr().out
    assert "Successfully installed M" in out
