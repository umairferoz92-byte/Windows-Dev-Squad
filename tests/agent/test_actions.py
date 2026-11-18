"""Tests for JSON action parsing."""

import pytest

from squad.agent import ActionError, parse_action


def test_parse_plain_json():
    data = parse_action('{"action": "edit_file", "args": {"path": "x"}}')
    assert data["action"] == "edit_file"


def test_parse_fenced_json():
    data = parse_action('```json\n{"action": "final"}\n```')
    assert data["action"] == "final"


def test_parse_no_json_raises():
    with pytest.raises(ActionError):
        parse_action("no json here")


def test_parse_missing_action_raises():
    with pytest.raises(ActionError):
        parse_action('{"not_an_action": true}')
