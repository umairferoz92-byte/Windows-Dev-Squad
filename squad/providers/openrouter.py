"""OpenRouter provider: plain HTTPS (httpx) against its OpenAI-compatible API.

- Blocks any model not in ``allowed_models``.
- HTTP 402 (out of credit / key limit) is a stop, never a retry.
- Records the model that actually answered.
- No automatic fallback is configured (we always request the exact model).
"""

from __future__ import annotations

import httpx

from squad.providers.base import ChatResponse, Provider, ProviderError, Usage


class OpenRouterProvider(Provider):
    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, allowed_models, client: httpx.Client | None = None):
        self.api_key = api_key
        self.allowed_models = set(allowed_models)
        self._client = client or httpx.Client(base_url=self.base_url, timeout=60.0)

    def chat(self, model: str, messages: list[dict], max_tokens: int = 1024) -> ChatResponse:
        if model not in self.allowed_models:
            raise ProviderError(f"model '{model}' is not in allowed_models")

        resp = self._client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
        )
        if resp.status_code == 402:
            raise ProviderError("HTTP 402: out of credit or key limit (stop, never retry)")
        if resp.status_code != 200:
            raise ProviderError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        actual_model = data.get("model") or model

        usage_raw = data.get("usage")
        usage = None
        if usage_raw:
            details = usage_raw.get("prompt_tokens_details") or {}
            usage = Usage(
                prompt_tokens=usage_raw.get("prompt_tokens"),
                completion_tokens=usage_raw.get("completion_tokens"),
                cached_tokens=details.get("cached_tokens", 0) or 0,
            )
        return ChatResponse(text=text, usage=usage, model=actual_model)
