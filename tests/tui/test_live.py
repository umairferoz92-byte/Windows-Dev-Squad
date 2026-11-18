"""Tests for the live TUI rendering."""

from squad.tui import AgentCard, render_approval, render_live


def test_render_live_shows_agent_cards():
    cards = [
        AgentCard("ironman", "coder", step=2, status="working", cost=0.001, budget=0.1),
        AgentCard("batman", "security", status="idle"),
    ]
    text = render_live(cards)
    assert "ironman" in text
    assert "coder" in text
    assert "working" in text
    assert "$0.001000 / $0.100000" in text
    assert "batman" in text


def test_render_live_handles_files():
    card = AgentCard("ironman", "coder", files=("src/main.py",))
    assert "src/main.py" in render_live([card])


def test_render_approval_shows_details():
    text = render_approval("edit_file", {"path": "x"}, "C:\\repo", "outside write scope")
    assert "edit_file" in text
    assert "C:\\repo" in text
    assert "outside write scope" in text
