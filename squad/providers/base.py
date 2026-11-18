"""Provider interface: one adapter per cloud model provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(RuntimeError):
    """A provider-level failure (auth, out of credit, HTTP error)."""


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int = 0


@dataclass(frozen=True)
class ChatResponse:
    text: str
    usage: Usage | None  # None = usage unreported (count at worst case)
    model: str | None = None  # the model that actually answered


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def chat(self, model: str, messages: list[dict], max_tokens: int = 1024) -> ChatResponse:
        raise NotImplementedError
