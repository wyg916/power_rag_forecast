from __future__ import annotations

import json

import pytest
import requests

from backend.app.ai_assistant.llm_providers.openai_compatible import (
    OpenAICompatibleProvider,
    ProviderRequestError,
)
from backend.app.ai_assistant.llm_router import LLMRouter
from backend.app.ai_assistant.llm_providers import DeepSeekProvider, KimiProvider, MiMoProvider


class _Response:
    def __init__(self, payload=None, *, status_code=200, lines=None):
        self.payload = payload or {}
        self.status_code = status_code
        self.lines = lines or []

    def json(self):
        return self.payload

    def iter_lines(self, decode_unicode=True):
        return iter(self.lines)

    def close(self):
        return None


def provider() -> OpenAICompatibleProvider:
    value = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://provider.example/v1",
        model="test-model",
        timeout_seconds=3,
    )
    value.name = "test"
    return value


def test_openai_adapter_chat_structured_tools_stream_and_health(monkeypatch):
    responses = iter([
        _Response({"data": [{"id": "test-model"}]}),
        _Response({"model": "test-model", "choices": [{"finish_reason": "stop", "message": {"content": "中文回答"}}]}),
        _Response({"choices": [{"message": {"content": json.dumps({"status": "ok"})}}]}),
        _Response({"choices": [{"message": {"content": "", "tool_calls": [{"id": "call_1", "function": {"name": "weather", "arguments": "{}"}}]}}]}),
        _Response(lines=['data: {"choices":[{"delta":{"content":"甲"}}]}', 'data: [DONE]']),
    ])
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: next(responses))
    active = provider()
    assert active.health()["available"]
    assert active.chat([{"role": "user", "content": "你好"}]) == "中文回答"
    assert active.structured_completion([], {"required": ["status"]}) == {"status": "ok"}
    assert active.tool_calls([], [{"type": "function"}])[0]["id"] == "call_1"
    assert list(active.chat_stream([])) == ["甲"]
    assert all(active.capabilities().values())


@pytest.mark.parametrize("status_code,retryable", [(400, False), (401, False), (429, True), (500, True), (503, True)])
def test_provider_marks_only_timeout_rate_limit_and_server_errors_retryable(monkeypatch, status_code, retryable):
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: _Response(status_code=status_code))
    with pytest.raises(ProviderRequestError) as raised:
        provider().chat([])
    assert raised.value.retryable is retryable


def test_timeout_is_retryable(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("late")
    monkeypatch.setattr(requests, "request", timeout)
    with pytest.raises(ProviderRequestError) as raised:
        provider().chat([])
    assert raised.value.reason == "timeout" and raised.value.retryable


class _FakeRemote:
    available = True
    default_model = "fake"
    reasoning_model = "fake"

    def __init__(self, name, error=None):
        self.name = name
        self.error = error

    def complete(self, messages, **kwargs):
        if self.error:
            raise self.error
        return type("Result", (), {
            "content": f"{self.name}-answer", "finish_reason": "stop",
            "reasoning_content": "", "tool_calls": (),
        })()


def test_auto_falls_back_on_retryable_failure_and_records_actual_provider(monkeypatch):
    router = LLMRouter()
    router._providers = {
        "deepseek": _FakeRemote("deepseek", ProviderRequestError("deepseek", "http_429", status_code=429, retryable=True)),
        "kimi": _FakeRemote("kimi"),
    }
    monkeypatch.setattr(router, "_auto_order", lambda task: ["deepseek", "kimi"])
    monkeypatch.setattr(router, "_configured", lambda name: True)
    content, status = router.generate_answer([], task_type="complex_analysis", requested_provider="auto")
    assert content == "kimi-answer"
    assert status["provider"] == "kimi" and status["fallback"] is True
    assert status["fallback_reason"] == "http_429"


def test_auto_does_not_fallback_on_auth_or_contract_failure(monkeypatch):
    router = LLMRouter()
    router._providers = {
        "deepseek": _FakeRemote("deepseek", ProviderRequestError("deepseek", "http_401", status_code=401, retryable=False)),
        "kimi": _FakeRemote("kimi"),
    }
    monkeypatch.setattr(router, "_auto_order", lambda task: ["deepseek", "kimi"])
    monkeypatch.setattr(router, "_configured", lambda name: True)
    with pytest.raises(RuntimeError, match="http_401"):
        router.generate_answer([], task_type="complex_analysis", requested_provider="auto")


def test_product_provider_model_ids_are_not_overridden_by_legacy_env(monkeypatch):
    monkeypatch.setenv("KIMI_MODEL", "legacy-kimi")
    monkeypatch.setenv("MIMO_MODEL", "legacy-mimo")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    assert KimiProvider().default_model == "kimi-k2.6"
    assert MiMoProvider().default_model == "mimo-v2.5"
    assert DeepSeekProvider().default_model == "deepseek-v4-flash"
