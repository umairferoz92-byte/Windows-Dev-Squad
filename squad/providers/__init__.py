"""Providers: one interface for cloud/local model backends (any LLM API key)."""

from __future__ import annotations

from squad.providers.base import ChatResponse, Provider, ProviderError, Usage
from squad.providers.models import all_allowed_models, role_allowed_models
from squad.providers.openrouter import OpenRouterProvider
from squad.providers.registry import get_provider
from squad.providers import factory

__all__ = [
    "ChatResponse",
    "Provider",
    "ProviderError",
    "Usage",
    "OpenRouterProvider",
    "get_provider",
    "factory",
    "all_allowed_models",
    "role_allowed_models",
]
