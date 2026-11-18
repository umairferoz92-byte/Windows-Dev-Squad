"""Tests for the scrubbed subprocess environment."""

import os

from squad.exec import scrubbed_env


def test_removes_secret_named_vars(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-secret")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA...")
    monkeypatch.setenv("KEEP_ME", "value")
    env = scrubbed_env()
    assert "OPENROUTER_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "AWS_ACCESS_KEY_ID" not in env
    assert env.get("KEEP_ME") == "value"


def test_keeps_path():
    env = scrubbed_env()
    assert "PATH" in env


def test_returns_a_copy(monkeypatch):
    env = scrubbed_env()
    env["INJECTED"] = "x"
    assert "INJECTED" not in os.environ
