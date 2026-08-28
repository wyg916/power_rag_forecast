from __future__ import annotations

import json

import pytest
import requests

from backend.app.ai_assistant.llm_providers.openai_compatible import (
    OpenAICompatibleProvider,
    ProviderRequestError,
)
from backend.app.ai_assistant import service
from backend.app.ai_assistant.llm_router import LLMRouter
from backend.app.ai_assistant.llm_providers import DeepSeekProvider, KimiProvider, MiMoProvider
from backend.app.ai_assistant.expert_answer_planner import plan_expert_answer
from backend.app.chatbi.planner import AnalysisPlanGenerationError, parse_analysis_plan
from scripts import final_blocker_cost_controlled_provider_smoke as provider_smoke


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
        "endpoint": "chat/completions",
        "request_mode": "non_stream",
        "stream": False,
        "model": "test-model",
        "message_count": 1,
        "content_types": ["text", "image_url"],
        "image_count": 1,
        "image_mimes": ["image/png"],
        "image_url_kinds": ["data"],
        "max_tokens": 0,
        "response_format": None,
    }
    assert result.diagnostics["response"]["content_part_types"] == ["text", "output_text"]
    assert result.diagnostics["response"]["request_id"] == "req_remote_1"
    assert "第一段" not in json.dumps(result.diagnostics, ensure_ascii=False)


def test_premium_answer_forces_model_call_without_application_token_limit(monkeypatch):
    captured: dict[str, object] = {}

    class CapturingRouter:
        def generate_answer(self, _messages, **kwargs):
            captured.update(kwargs)
            return "高阶模式正常", {
                "provider": "kimi", "model": "kimi-k2.6", "logical_alias": "PREMIUM",
                "input_tokens": 8, "output_tokens": 6, "latency_ms": 1,
                "estimated_cost": 0, "currency": "CNY", "fallback": False,
            }

    monkeypatch.setattr(service, "LLMRouter", CapturingRouter)
    monkeypatch.setenv("AI_ASSISTANT_LLM_ENABLED", "1")
    monkeypatch.setattr(service, "rag_enabled", lambda: False)
    monkeypatch.setattr(service, "get_conversation_state", lambda _identity: None)
    monkeypatch.setattr(service, "_execute_tools", lambda *_args, **_kwargs: [])

    result = service.answer_chat_accurate(
        "你好",
        requested_tier="premium",
        premium_confirmed=True,
        logical_alias="PREMIUM",
    )

    assert captured["requested_tier"] == "premium"
    assert captured["premium_confirmed"] is True
    assert captured["max_tokens"] is None
    assert result["model_provider_used"] == "kimi"


def _deepseek_plan_payload() -> dict:
    return {
        "datasets": ["market_price_history"],
        "metrics": ["avg_day_ahead_price"],
        "dimensions": [],
        "filters": [],
        "group_by": [],
        "order_by": [],
        "limit": 100,
        "joins": [],
        "chart_intent": "table",
        "analysis_mode": "aggregate",
        "clarification_required": False,
        "clarification_question": None,
    }


def _deepseek_response(*, content=None, reasoning_content=None, choices=True) -> dict:
    payload = {
        "id": "safe-request-id",
        "model": "deepseek-chat",
        "object": "chat.completion",
        "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
        "choices": [],
    }
    if choices:
        message = {"role": "assistant", "content": content}
        if reasoning_content is not None:
            message["reasoning_content"] = reasoning_content
        payload["choices"] = [{"finish_reason": "stop", "message": message}]
    return payload


def test_deepseek_shape_captures_non_stream_observability_without_content(monkeypatch):
    response = _Response(
        _deepseek_response(content=json.dumps(_deepseek_plan_payload(), ensure_ascii=False))
    )
    response.headers = {"content-type": "application/json", "x-request-id": "safe-header-id"}
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)

    result = provider().complete(
        [{"role": "user", "content": "sanitized"}],
        model="deepseek-chat",
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    diagnostics = result.diagnostics
    assert diagnostics["request"] == {
        "endpoint": "chat/completions",
        "request_mode": "non_stream",
        "stream": False,
        "model": "deepseek-chat",
        "message_count": 1,
        "content_types": ["text"],
        "image_count": 0,
        "image_mimes": [],
        "image_url_kinds": [],
        "max_tokens": 400,
        "response_format": "json_object",
    }
    assert diagnostics["response"]["request_id"] == "safe-header-id"
    assert diagnostics["response"]["body_present"] is True
    assert diagnostics["response"]["body_keys"] == ["choices", "id", "model", "object", "usage"]
    assert diagnostics["response"]["choice_count"] == 1
    assert diagnostics["response"]["message_present"] is True
    assert diagnostics["response"]["content_present"] is True
    assert diagnostics["response"]["adapter_parse_result"] == "PASS_CONTENT"
    assert diagnostics["response"]["usage"]["capture_status"] == "CAPTURED"
    serialized = json.dumps(diagnostics, ensure_ascii=False)
    assert "market_price_history" not in serialized
    assert "avg_day_ahead_price" not in serialized


@pytest.mark.parametrize(
    ("payload", "parse_result"),
    [
        (_deepseek_response(content=""), "FAIL_CONTENT_EMPTY"),
        (
            _deepseek_response(content="", reasoning_content="internal reasoning only"),
            "FAIL_REASONING_ONLY",
        ),
        (_deepseek_response(choices=False), "FAIL_CHOICES_MISSING"),
    ],
)
def test_deepseek_empty_shapes_fail_closed_with_precise_diagnostics(monkeypatch, payload, parse_result):
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: _Response(payload))
    with pytest.raises(ProviderRequestError) as raised:
        provider().complete([], model="deepseek-chat", max_tokens=400)
    assert raised.value.reason == "empty_response"
    diagnostics = raised.value.diagnostics["response"]
    assert diagnostics["adapter_parse_result"] == parse_result
    assert diagnostics["usage"]["capture_status"] == "CAPTURED"


def test_deepseek_missing_usage_is_explained_not_reported_as_unknown(monkeypatch):
    payload = _deepseek_response(content=json.dumps(_deepseek_plan_payload()))
    payload.pop("usage")
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: _Response(payload))
    result = provider().complete([], model="deepseek-chat", max_tokens=400)
    assert result.diagnostics["response"]["usage"] == {
        "capture_status": "USAGE_NOT_RETURNED_BY_PROVIDER",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_analysis_plan_offline_fixtures_cover_plain_fenced_malformed_and_schema_invalid():
    valid = json.dumps(_deepseek_plan_payload(), ensure_ascii=False)
    assert parse_analysis_plan(valid).metrics == ["avg_day_ahead_price"]
    assert parse_analysis_plan(f"```json\n{valid}\n```").datasets == ["market_price_history"]

    with pytest.raises(AnalysisPlanGenerationError):
        parse_analysis_plan('{"datasets": [}')
    with pytest.raises(AnalysisPlanGenerationError):
        parse_analysis_plan(json.dumps({**_deepseek_plan_payload(), "limit": "not-an-integer"}))


def test_stream_fixture_aggregates_content_chunks_without_promoting_reasoning(monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"internal"}}]}',
        'data: {"choices":[{"delta":{"content":"{\\"datasets\\":"}}]}',
        'data: {"choices":[{"delta":{"content":"[]}"}}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: _Response(lines=lines))
    assert list(provider().chat_stream([])) == ['{"datasets":', "[]}"]


def test_cost_controlled_deepseek_smoke_uses_data_planner_endpoint_model(monkeypatch):
    captured: dict[str, object] = {}

    class FakeDeepSeek:
        available = True
        api_key = "not-persisted"

        def complete(self, messages, **options):
            captured["messages"] = messages
            captured["options"] = options
            return provider_smoke.CompletionResult(
                content=json.dumps(_deepseek_plan_payload()),
                model="deepseek-chat",
                finish_reason="stop",
                input_tokens=80,
                output_tokens=40,
                diagnostics={
                    "request": {
                        "endpoint": "chat/completions",
                        "request_mode": "non_stream",
                        "stream": False,
                        "model": options["model"],
                        "max_tokens": options["max_tokens"],
                        "response_format": "json_object",
                    },
                    "response": {
                        "http_status": 200,
                        "request_id": "safe-request-id",
                        "body_present": True,
                        "body_type": "dict",
                        "body_keys": ["choices", "id", "model", "usage"],
                        "choice_count": 1,
                        "message_present": True,
                        "message_keys": ["content", "role"],
                        "content_present": True,
                        "content_chars": 100,
                        "reasoning_content_present": False,
                        "reasoning_chars": 0,
                        "tool_calls_count": 0,
                        "finish_reason": "stop",
                        "response_model": "deepseek-chat",
                        "adapter_parse_result": "PASS_CONTENT",
                        "usage": {
                            "capture_status": "CAPTURED",
                            "prompt_tokens": 80,
                            "completion_tokens": 40,
                            "total_tokens": 120,
                        },
                        "latency_ms": 1.0,
                    },
                },
            )

    monkeypatch.setattr(provider_smoke, "DeepSeekProvider", FakeDeepSeek)
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    record = provider_smoke._deepseek_analysis_plan([])

    assert captured["options"] == {
        "model": "deepseek-v4-flash",
        "temperature": 0,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }
    assert record["status"] == "PASS"
    assert record["logical_alias"] == "DATA_PLANNER"
    assert record["selected_model"] == "deepseek-v4-flash"
    assert record["schema_validation"] == "PASS"
    assert record["semantic_validation"] == "PASS"


@pytest.mark.parametrize(
    "case_name,answer,citations,grounding,expected_grounding,expected_citation",
    [
        (
            "A_correct_answer_correct_citation",
            "这个文件中的 PROJECT_CODE 是 ALPHA-7281。",
            [{"attachment_id": "att_alpha", "file_name": "alpha-7281.txt", "source_id": "attachment:att_alpha:achunk_1"}],
            {"source_ids": ["attachment:att_alpha:achunk_1"], "chunk_count": 1, "enterprise_kb_chunk_count": 0, "only_selected_attachments_mode": True},
            True,
            True,
        ),
        (
            "B_correct_answer_no_citation",
            "这个文件中的 PROJECT_CODE 是 ALPHA-7281。",
            [],
            {"source_ids": ["attachment:att_alpha:achunk_1"], "chunk_count": 1, "enterprise_kb_chunk_count": 0, "only_selected_attachments_mode": True},
            True,
            False,
        ),
        (
            "C_wrong_answer_correct_citation",
            "这个文件中的 PROJECT_CODE 是 BETA-0000。",
            [{"attachment_id": "att_alpha", "file_name": "alpha-7281.txt", "source_id": "attachment:att_alpha:achunk_1"}],
            {"source_ids": ["attachment:att_alpha:achunk_1"], "chunk_count": 1, "enterprise_kb_chunk_count": 0, "only_selected_attachments_mode": True},
            False,
            True,
        ),
        (
            "D_wrong_answer_no_citation",
            "这个文件中的 PROJECT_CODE 是 BETA-0000。",
            [],
            {"source_ids": ["attachment:att_alpha:achunk_1"], "chunk_count": 1, "enterprise_kb_chunk_count": 0, "only_selected_attachments_mode": True},
            False,
            False,
        ),
        (
            "E_wrong_attachment_id",
            "这个文件中的 PROJECT_CODE 是 ALPHA-7281。",
            [{"attachment_id": "att_other", "file_name": "alpha-7281.txt", "source_id": "attachment:att_other:achunk_1"}],
            {"source_ids": ["attachment:att_alpha:achunk_1"], "chunk_count": 1, "enterprise_kb_chunk_count": 0, "only_selected_attachments_mode": True},
            True,
            False,
        ),
        (
            "F_enterprise_kb_instead_of_selected_attachment",
            "这个文件中的 PROJECT_CODE 是 ALPHA-7281。",
            [],
            {"source_ids": [], "chunk_count": 0, "enterprise_kb_chunk_count": 1, "only_selected_attachments_mode": False},
            False,
            False,
        ),
    ],
)
def test_attachment_evaluator_independently_proves_grounding_and_citation(
    case_name, answer, citations, grounding, expected_grounding, expected_citation
):
    uploaded_id = "att_alpha"
    payload = {
        "answer": answer,
        "attachment_citations": citations,
        "attachment_grounding": grounding,
    }
    evidence = provider_smoke._evaluate_attachment_evidence(payload, uploaded_id)

    assert evidence["GROUNDING_PASS"] is expected_grounding, case_name
    assert evidence["CITATION_PASS"] is expected_citation, case_name
    assert evidence["ATTACHMENT_ID"] == uploaded_id
    assert evidence["FILE_NAME"] == "alpha-7281.txt"
    assert evidence["QUESTION"] == "这个文件中的 PROJECT_CODE 是什么？"
    assert evidence["EXPECTED_FACT"] == "ALPHA-7281"
    assert len(evidence["ANSWER_TEXT_REDACTED"]) <= 300
    assert set(evidence) == {
        "ATTACHMENT_ID", "FILE_NAME", "QUESTION", "EXPECTED_FACT",
        "ANSWER_TEXT_REDACTED", "ANSWER_CONTAINS_EXPECTED_FACT",
        "RETRIEVED_ATTACHMENT_CHUNK_COUNT", "RETRIEVED_ATTACHMENT_SOURCE_IDS",
        "ENTERPRISE_KB_CHUNK_COUNT", "ONLY_SELECTED_ATTACHMENTS_MODE", "GROUNDING_PASS",
        "CITATION_COUNT", "CITATION_ATTACHMENT_IDS", "CITATION_FILE_NAMES",
        "CITATION_SOURCE_IDS", "CITATION_PASS",
    }


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
