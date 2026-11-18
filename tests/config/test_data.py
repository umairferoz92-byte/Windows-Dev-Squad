"""Tests for the data-dir template copy."""

from squad.config.data import active_config, ensure_template


def test_ensure_template_copies_once(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LA"))
    template = tmp_path / "squad.yaml"
    template.write_text("repo: {}\n", encoding="utf-8")
    active = ensure_template("squad.yaml", str(template))
    assert active.read_text(encoding="utf-8") == "repo: {}\n"
    # idempotent: a later template edit is not copied over the active file
    template.write_text("changed\n", encoding="utf-8")
    assert ensure_template("squad.yaml", str(template)).read_text(encoding="utf-8") == "repo: {}\n"


def test_active_config_returns_data_path(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LA"))
    template = tmp_path / "g.yaml"
    template.write_text("version: 1\n", encoding="utf-8")
    path = active_config("guard.yaml", str(template))
    assert str(tmp_path / "LA" / "squad" / "guard.yaml") in str(path)
