"""Provider registry: dynamic provider registration.

Register providers by name. The default OpenRouter provider is registered on import,
but any module can register additional providers. Lookup is case-insensitive."""

from __future__ import annotations

_PROVIDERS: dict[str, type] = {}

# Default OpenRouter provider — registered on import
from squad.providers.openrouter import OpenRouterProvider as _OpenRouterProvider  # noqa: E402  # avoids circular import; registered after _PROVIDERS

_PROVIDERS["openrouter"] = _OpenRouterProvider


def register(name: str, cls: type) -> None:
    """Register a provider class under *name* (lowercased)."""
    _PROVIDERS[name.lower()] = cls


def get_provider(name: str, **kwargs):
    """Instantiate and return a provider by *name* (case-insensitive).

    Raises ValueError if the provider is not registered.
    """
    cls = _PROVIDERS.get(name.lower())
    if cls is None:
        raise ValueError(f"unknown provider '{name}' (allowed: {sorted(_PROVIDERS)})")
    return cls(**kwargs)


def list_providers() -> list[str]:
    """Return a sorted list of registered provider names."""
    return sorted(_PROVIDERS.keys())
