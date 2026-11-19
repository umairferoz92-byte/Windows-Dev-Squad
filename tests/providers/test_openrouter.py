"""Tests for the OpenRouter provider (fully mocked, offline)."""

import httpx
import pytest

from squad.providers import OpenRouterProvider, ProviderError

MODEL = "openrouter/test/model"


def _provider(handler, allowed=(MODEL,)):
    client = httpx.Client(base_url="https://openrouter.ai/api/v1", transport=httpx.MockTransport(handler))
    return OpenRouterProvider("sk-test", allowed, client=client)


def test_chat_success_with_usage():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": MODEL,
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    resp = _provider(handler).chat(MODEL, [{"role": "user", "content": "hi"}])
    assert resp.text == "hi"
    assert resp.model == MODEL
    assert resp.usage.prompt_tokens == 10
    assert resp.usage.completion_tokens == 5


def test_chat_402_is_a_stop():
    def handler(request):
        return httpx.Response(402, json={"error": {"message": "insufficient credits"}})

    with pytest.raises(ProviderError):
        _provider(handler).chat(MODEL, [{"role": "user", "content": "hi"}])


def test_chat_model_not_allowed_is_blocked():
    def handler(request):
        return httpx.Response(200, json={})

    with pytest.raises(ProviderError):
        _provider(handler, allowed=("other/model",)).chat(MODEL, [])


def test_chat_unreported_usage():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    resp = _provider(handler).chat(MODEL, [{"role": "user", "content": "x"}])
    assert resp.text == "ok"
    assert resp.usage is None  # unreported


def test_chat_http_error_raises():
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(ProviderError):
        _provider(handler).chat(MODEL, [])
