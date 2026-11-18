"""Provider factory: pick a cloud/local LLM backend + its API key.

The chatbot and ``squad providers test`` / ``squad run`` all resolve their
provider through here. Selection order (first that yields a usable key, or a
local endpoint that needs no key):

1. ``SQUAD_LLM_PROVIDER`` env var — explicit choice.
2. ``provider`` key under ``squad.yaml`` → ``models`` (e.g. ``openai``).
3. First provider whose API key is present in os.environ.
4. A local endpoint (Ollama / LM Studio) as a free fallback.

Every provider is optional: with no key and no local server the LLM tier
raises NoKey and the chatbot falls back to offline answers, exactly as before.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from squad.providers.anthropic import AnthropicProvider
from squad.providers.base import Provider
from squad.providers.openai_compat import OpenAICompatibleProvider


@dataclass(frozen=True)
class _Spec:
    name: str
    key_env: str | None
    base_url: str
    cls: type
    free: bool = False
    # Some OpenAI-compatible hosts send the key as a plain header, not Bearer.
    key_header: str = "Authorization"
    key_prefix: str = "Bearer "


# Known providers. ``free=True`` ones work without any key (local servers).
_SPECS: dict[str, _Spec] = {
    "openai": _Spec("openai", "OPENAI_API_KEY", "https://api.openai.com/v1", OpenAICompatibleProvider),
    "openrouter": _Spec("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", OpenAICompatibleProvider),
    "anthropic": _Spec("anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1", AnthropicProvider),
    "groq": _Spec("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", OpenAICompatibleProvider, free=True),
    "mistral": _Spec("mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1", OpenAICompatibleProvider),
    "together": _Spec("together", "TOGETHER_API_KEY", "https://api.together.xyz/v1", OpenAICompatibleProvider),
    "fireworks": _Spec("fireworks", "FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1", OpenAICompatibleProvider),
    # Google Gemini exposes an OpenAI-compatible endpoint (key via query/header).
    "gemini": _Spec("gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", OpenAICompatibleProvider),
    # Free, fully-local endpoints that need no API key.
    "ollama": _Spec("ollama", None, "http://localhost:11434/v1", OpenAICompatibleProvider, free=True),
    "lmstudio": _Spec("lmstudio", None, "http://localhost:1234/v1", OpenAICompatibleProvider, free=True),
}

# Aliases for convenience.
_ALIASES = {"claude": "anthropic", "local": "ollama", "openai_compatible": "openai"}

_ALIAS_MAP: dict[str, str] = {}
for _k, _v in _SPECS.items():
    _ALIAS_MAP[_k] = _k
for _alias, _target in _ALIASES.items():
    _ALIAS_MAP[_alias] = _target


def provider_names() -> list[str]:
    """Sorted, de-duplicated canonical provider names (aliases hidden)."""
    return sorted(_SPECS)


def provider_key_env(name: str) -> str | None:
    """Return the env-var name that holds *name*'s API key (or None for free
    local providers like Ollama/LM Studio that need no key)."""
    key = (name or "").strip().lower()
    target = _ALIAS_MAP.get(key)
    spec = _SPECS.get(target if target else key)
    return spec.key_env if spec else None


# --- Free local Ollama helpers ----------------------------------------------
import httpx as _httpx


def ollama_base_url() -> str:
    """Ollama's OpenAI-compatible endpoint (default localhost:11434/v1)."""
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")


def ollama_running(timeout: float = 1.5) -> bool:
    """True when a local Ollama server responds on the OpenAI endpoint."""
    try:
        r = _httpx.get(ollama_base_url() + "/models", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def ollama_models(timeout: float = 2.0) -> list[str]:
    """List installed Ollama model names, or [] when the server is unreachable."""
    try:
        r = _httpx.get(ollama_base_url() + "/models", timeout=timeout)
        if r.status_code != 200:
            return []
        data = r.json()
        return sorted(m.get("id") or m.get("model") or "" for m in data.get("data") or [] if (m.get("id") or m.get("model")))
    except Exception:
        return []


def _resolve_name(preferred: str | None) -> str:
    if preferred:
        key = preferred.strip().lower()
        target = _ALIAS_MAP.get(key)
        if target:
            return target
        # Unknown name → fall through to auto-detect rather than crash.
    for name, spec in _SPECS.items():
        if spec.key_env and os.environ.get(spec.key_env):
            return name
    # No key anywhere → prefer a free local endpoint if it is reachable later;
    # just pick Ollama so `providers test` can try localhost.
    for name in ("ollama", "lmstudio"):
        if name in _SPECS:
            return name
    return "openrouter"


def resolve_provider(preferred: str | None = None, config: dict | None = None):
    """Return the best (provider_name, api_key) for the environment.

    Selection order:
    1. ``SQUAD_LLM_PROVIDER`` env var (unless *preferred* explicitly passed).
    2. ``provider`` key under squad.yaml ``models``.
    3. First provider whose API key is present in os.environ.
    4. A free local endpoint (Ollama / LM Studio).
    """
    if preferred is None:
        preferred = os.environ.get("SQUAD_LLM_PROVIDER")
    name = _resolve_name(preferred or (config or {}).get("provider"))
    spec = _SPECS[name]
    api_key = os.environ.get(spec.key_env) if spec.key_env else ""
    return name, api_key, spec


def build_provider(
    name: str,
    api_key: str,
    allowed_models,
) -> Provider:
    """Instantiate a provider instance for *name*."""
    spec = _SPECS[name]
    if spec.cls is AnthropicProvider:
        return AnthropicProvider(api_key, allowed_models, base_url=spec.base_url)
    return OpenAICompatibleProvider(
        api_key,
        allowed_models,
        base_url=spec.base_url,
        api_key_header=spec.key_header,
        api_key_prefix=spec.key_prefix,
    )