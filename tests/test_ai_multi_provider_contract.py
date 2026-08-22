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
from backend.app.ai_assistant.expert_answer_planner import plan_expert_answer


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


def test_openai_adapter_normalizes_multipart_content_and_records_safe_diagnostics(monkeypatch):
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: _Response({
        "id": "req_remote_1",
        "model": "test-model",
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": [
                {"type": "text", "text": "第一段"},
                {"type": "output_text", "text": {"value": "第二段"}},
            ]},
        }],
    }))
    result = provider().complete([{
        "role": "user",
        "content": [
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
        ],
    }])
    assert result.content == "第一段\n第二段"
    assert result.diagnostics["request"] == {
        "model": "test-model",
        "message_count": 1,
        "content_types": ["text", "image_url"],
        "image_count": 1,
        "image_mimes": ["image/png"],
        "image_url_kinds": ["data"],
        "max_tokens": 1400,
        "response_format": None,
    }
    assert result.diagnostics["response"]["content_part_types"] == ["text", "output_text"]
    assert result.diagnostics["response"]["request_id"] == "req_remote_1"
    assert "第一段" not in json.dumps(result.diagnostics, ensure_ascii=False)


def test_structured_completion_reports_types_without_persisting_raw_content(monkeypatch):
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: _Response({
        "choices": [{"message": {"content": '{"status":null,"steps":"bad"}'}}]
    }))
    schema = {
        "type": "object",
        "required": ["status", "steps"],
        "properties": {"status": {"type": "string"}, "steps": {"type": "array"}},
    }
    with pytest.raises(ProviderRequestError) as raised:
        provider().structured_completion([], schema)
    assert raised.value.reason == "structured_response_schema_mismatch"
    structure = raised.value.diagnostics["structured_output"]
    assert structure["value_types"] == {"status": "NoneType", "steps": "str"}
    assert structure["schema_issues"] == ["$.status:type", "$.steps:type"]
    assert "bad" not in json.dumps(raised.value.diagnostics)


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
            "reasoning_content": "", "tool_calls": (), "model": "fake",
            "input_tokens": 10, "output_tokens": 5, "latency_ms": 1.0,
        })()


def test_general_auto_falls_back_once_from_mimo_to_deepseek(monkeypatch):
    router = LLMRouter()
    router._providers = {
        "mimo": _FakeRemote("mimo", ProviderRequestError("mimo", "http_429", status_code=429, retryable=True)),
        "deepseek": _FakeRemote("deepseek"),
    }
    content, status = router.generate_answer(
        [], task_type="daily_chat", requested_provider="auto", logical_alias="GENERAL_DEFAULT"
    )
    assert content == "deepseek-answer"
    assert status["provider"] == "deepseek" and status["fallback_count"] == 1
    assert status["fallback_from"] == "mimo"
    assert status["fallback_reason"] == "http_429"


def test_complex_deepseek_failure_never_silently_uses_kimi():
    router = LLMRouter()
    router._providers = {
        "deepseek": _FakeRemote("deepseek", ProviderRequestError("deepseek", "http_429", status_code=429, retryable=True)),
        "kimi": _FakeRemote("kimi"),
    }
    with pytest.raises(RuntimeError, match="http_429"):
        router.generate_answer([], task_type="complex_analysis", requested_provider="auto")


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


def test_kimi_k26_normalizes_provider_neutral_temperature(monkeypatch):
    captured = []

    def request(*args, **kwargs):
        captured.append(kwargs["json"])
        if kwargs["json"].get("stream"):
            return _Response(lines=['data: {"choices":[{"delta":{"content":"甲"}}]}', 'data: [DONE]'])
        return _Response({"model": "kimi-k2.6", "choices": [{"finish_reason": "stop", "message": {"content": "成功"}}]})

    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    active = KimiProvider()
    assert active.complete([{"role": "user", "content": "你好"}], temperature=0).content == "成功"
    assert list(active.chat_stream([{"role": "user", "content": "你好"}], temperature=0)) == ["甲"]
    assert all(item["temperature"] == 0.6 for item in captured)
    assert all(item["thinking"] == {"type": "disabled"} for item in captured)


def test_forecast_overview_reserves_complex_answer_budget():
    plan = plan_expert_answer("forecast_overview", model_provider="deepseek")
    assert plan.task_type == "complex_analysis"
    assert plan.max_tokens == 4096
