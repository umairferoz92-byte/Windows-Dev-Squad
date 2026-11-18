"""Tests for the ``--setup-help`` content."""

from squad.cli.setup_help import setup_help_text


def test_setup_help_covers_required_steps():
    text = setup_help_text()
    assert "New-LocalUser" in text
    assert "net user" in text
    assert "Windows Sandbox" in text
    assert "Windows Filtering Platform" in text
    assert '"verified": true' in text
