"""OpenAI-compatible provider: plain HTTPS (httpx) against any chat/completions
endpoint that speaks the OpenAI protocol.

Covers OpenAI, OpenRouter, Groq, Together, Fireworks, LM Studio, Ollama, and
any other host that implements ``POST /v1/chat/completions``. Point ``base_url``
at the host; supply ``api_key`` (many free/local hosts accept a dummy key or
omit it entirely).

- Blocks any model not in ``allowed_models`` (skip the check with ``None``).
- HTTP 402 / 429 / 401 are surfaced as ProviderError with a clear message.
- Records the model that actually answered.
"""

from __future__ import annotations

import httpx

from squad.providers.base import ChatResponse, Provider, ProviderError, Usage


class OpenAICompatibleProvider(Provider):
    name = "openai_compatible"

    def __init__(
        self,
        api_key: str,
        allowed_models,
        base_url: str = "https://api.openai.com/v1",
        api_key_header: str = "Authorization",
        api_key_prefix: str = "Bearer ",
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.allowed_models = set(allowed_models) if allowed_models else None
        self.base_url = base_url.rstrip("/")
        self.api_key_header = api_key_header
        self.api_key_prefix = api_key_prefix
        self._client = client or httpx.Client(base_url=self.base_url, timeout=60.0)

    def _auth_headers(self) -> dict:
        if not self.api_key:
            return {}
        if self.api_key_header == "Authorization":
            return {"Authorization": f"{self.api_key_prefix}{self.api_key}"}
        return {self.api_key_header: self.api_key}

    def chat(self, model: str, messages: list[dict], max_tokens: int = 1024) -> ChatResponse:
        if self.allowed_models is not None and model not in self.allowed_models:
            raise ProviderError(f"model '{model}' is not in allowed_models")

        resp = self._client.post(
            "/chat/completions",
            headers=self._auth_headers(),
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
        )
        if resp.status_code in (402, 401, 429):
            reason = {402: "out of credit", 401: "unauthorized", 429: "rate limited"}[resp.status_code]
            raise ProviderError(f"{reason} (HTTP {resp.status_code}): {resp.text[:200]}")
        if resp.status_code != 200:
            raise ProviderError(f"provider HTTP {resp.status_code}: {resp.text[:200]}")

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
