"""Tests for the provider factory (multi-provider / any-key resolution)."""

from __future__ import annotations

from pathlib import Path

from squad.providers import factory
from squad.providers.anthropic import AnthropicProvider
from squad.providers.openai_compat import OpenAICompatibleProvider


def test_provider_names_are_unique_and_canonical():
    names = factory.provider_names()
    # Canonical only, no alias duplicates.
    assert "openai" in names and "anthropic" in names and "openrouter" in names
    assert "gemini" in names and "groq" in names and "ollama" in names
    assert "claude" not in names and "local" not in names
    assert len(names) == len(set(names))


def test_resolve_preferred_alias_maps_to_canonical():
    name, _key, spec = factory.resolve_provider(preferred="claude")
    assert name == "anthropic"
    assert spec.cls is AnthropicProvider


def test_resolve_preferred_unknown_falls_back():
    name, _key, _spec = factory.resolve_provider(preferred="totally-unknown-provider")
    assert isinstance(name, str) and name  # never crashes


def test_resolve_picks_first_available_key(monkeypatch):
    import squad.config.data as cdata

    monkeypatch.setattr(cdata, "data_dir", lambda: Path("nonexistent-dir-for-tests"))
    monkeypatch.setenv("GROQ_API_KEY", "grok-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SQUAD_LLM_PROVIDER", raising=False)
    name, key, spec = factory.resolve_provider()
    assert name == "groq" and key == "grok-test"


def test_resolve_no_keys_returns_free_local(monkeypatch):
    import squad.config.data as cdata

    monkeypatch.setattr(cdata, "data_dir", lambda: Path("nonexistent-dir-for-tests"))
    # No keys set -> prefer a free local endpoint (no key needed).
    for k in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "MISTRAL_API_KEY",
        "TOGETHER_API_KEY",
        "FIREWORKS_API_KEY",
        "OLLAMA_API_KEY",
        "SQUAD_LLM_PROVIDER",
    ):
        monkeypatch.delenv(k, raising=False)
    name, _key, spec = factory.resolve_provider()
    assert spec.free is True
    assert name in ("ollama", "lmstudio")


def test_resolve_config_provider_wins(monkeypatch):
    import squad.config.data as cdata

    monkeypatch.setattr(cdata, "data_dir", lambda: Path("nonexistent-dir-for-tests"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SQUAD_LLM_PROVIDER", raising=False)
    name, _key, _spec = factory.resolve_provider(config={"provider": "openai"})
    assert name == "openai"


def test_build_provider_classes():
    assert isinstance(factory.build_provider("anthropic", "sk-x", None), AnthropicProvider)
    assert isinstance(factory.build_provider("openai", "sk-x", None), OpenAICompatibleProvider)
    assert isinstance(factory.build_provider("ollama", "", None), OpenAICompatibleProvider)
