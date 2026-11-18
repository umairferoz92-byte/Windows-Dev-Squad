"""Tests for config loading (yaml.safe_load only)."""

from squad.checks.config import load_yaml


def test_load_yaml_returns_dict(tmp_path):
    path = tmp_path / "squad.yaml"
    path.write_text("repo:\n  check_commands:\n    test: [a, b]\n", encoding="utf-8")
    data = load_yaml(str(path))
    assert data["repo"]["check_commands"]["test"] == ["a", "b"]


def test_load_yaml_missing_file_returns_empty(tmp_path):
    assert load_yaml(str(tmp_path / "nope.yaml")) == {}


def test_load_yaml_non_dict_returns_empty(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    assert load_yaml(str(path)) == {}
