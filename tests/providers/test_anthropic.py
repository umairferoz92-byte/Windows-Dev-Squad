"""Tests for the Anthropic (Claude) provider (fully mocked, offline)."""
from __future__ import annotations

import httpx
import pytest

from squad.providers.anthropic import AnthropicProvider
from squad.providers.base import ProviderError

MODEL = "claude-sonnet-4-20250514"


def _provider(handler, allowed=(MODEL,)):
    client = httpx.Client(
        base_url="https://api.anthropic.com/v1", transport=httpx.MockTransport(handler)
    )
    return AnthropicProvider("sk-ant-test", allowed, client=client)


def test_chat_success_with_usage():
    import json

    def handler(request):
        body = json.loads(request.read())
        assert b"/v1/messages" in request.url.path.encode()
        # system is lifted out of the conversation.
        assert body["system"] == "be nice"
        assert body["messages"] == [{"role": "user", "content": "hi"}]
        return httpx.Response(
            200,
            json={
                "model": MODEL,
                "content": [{"type": "text", "text": "hi there"}],
                "usage": {"input_tokens": 8, "output_tokens": 3},
            },
        )

    resp = _provider(handler).chat(
        MODEL,
        [{"role": "system", "content": "be nice"}, {"role": "user", "content": "hi"}],
    )
    assert resp.text == "hi there"
    assert resp.model == MODEL
    assert resp.usage.prompt_tokens == 8
    assert resp.usage.completion_tokens == 3


def test_chat_402_is_a_stop():
    def handler(request):
        return httpx.Response(402, json={"error": {"message": "billing"}})

    with pytest.raises(ProviderError):
        _provider(handler).chat(MODEL, [{"role": "user", "content": "hi"}])


def test_chat_model_not_allowed_is_blocked():
    def handler(request):
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError):
        _provider(handler, allowed=("other/model",)).chat(MODEL, [])


def test_chat_unreported_usage():
    def handler(request):
        return httpx.Response(
            200,
            json={"model": MODEL, "content": [{"type": "text", "text": "ok"}]},
        )

    resp = _provider(handler).chat(MODEL, [{"role": "user", "content": "x"}])
    assert resp.text == "ok"
    assert resp.usage is None


def test_chat_http_error_raises():
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(ProviderError):
        _provider(handler).chat(MODEL, [{"role": "user", "content": "hi"}])