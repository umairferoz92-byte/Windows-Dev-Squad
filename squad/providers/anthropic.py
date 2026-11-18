"""Anthropic (Claude) provider: the Messages API at api.anthropic.com.

Differs from the OpenAI-compatible shape: POST /v1/messages, a top-level
``max_tokens`` and ``system`` string, and a ``anthropic-version`` header.
"""
from __future__ import annotations

import httpx

from squad.providers.base import ChatResponse, Provider, ProviderError, Usage

_DEFAULT_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        allowed_models,
        base_url: str = "https://api.anthropic.com/v1",
        version: str = _DEFAULT_VERSION,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.allowed_models = set(allowed_models) if allowed_models else None
        self.base_url = base_url.rstrip("/")
        self.version = version
        self._client = client or httpx.Client(base_url=self.base_url, timeout=60.0)

    def _split_system(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Anthropic wants system as a separate top-level field."""
        system = None
        rest: list[dict] = []
        for m in messages:
            if m.get("role") == "system" and system is None:
                system = m.get("content")
            else:
                rest.append(m)
        return (system, rest)

    def chat(self, model: str, messages: list[dict], max_tokens: int = 1024) -> ChatResponse:
        if self.allowed_models is not None and model not in self.allowed_models:
            raise ProviderError(f"model '{model}' is not in allowed_models")

        system, convo = self._split_system(messages)
        payload: dict = {"model": model, "messages": convo, "max_tokens": max_tokens}
        if system:
            payload["system"] = system

        resp = self._client.post(
            "/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.version,
                "content-type": "application/json",
            },
            json=payload,
        )
        if resp.status_code in (401, 402, 403, 429):
            reason = {
                401: "unauthorized",
                402: "out of credit",
                403: "forbidden",
                429: "rate limited",
            }[resp.status_code]
            raise ProviderError(f"{reason} (HTTP {resp.status_code}): {resp.text[:200]}")
        if resp.status_code != 200:
            raise ProviderError(f"anthropic HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        # text blocks are the content; usage is nested in data["usage"].
        text = "".join(
            b.get("text", "")
            for b in (data.get("content") or [])
            if b.get("type") == "text"
        )
        usage_raw = data.get("usage")
        usage = None
        if usage_raw:
            usage = Usage(
                prompt_tokens=usage_raw.get("input_tokens"),
                completion_tokens=usage_raw.get("output_tokens"),
                cached_tokens=usage_raw.get("cache_read_input_tokens", 0) or 0,
            )
        return ChatResponse(text=text.strip(), usage=usage, model=data.get("model") or model)