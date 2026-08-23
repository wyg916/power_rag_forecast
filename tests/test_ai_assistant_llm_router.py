from __future__ import annotations

from backend.app.ai_assistant.llm_providers import ProviderRequestError
from backend.app.ai_assistant.llm_router import LLMRouter, sanitize_error
from backend.app.ai_assistant import service


class FakeDeepSeekProvider:
    name = "deepseek"
    default_model = "deepseek-chat"
    reasoning_model = "deepseek-reasoner"
    available = True

    def chat(self, messages, **kwargs):
        return "deepseek answer"

    def complete(self, messages, **kwargs):
        return type("Result", (), {
            "content": "deepseek answer",
            "finish_reason": "stop",
            "reasoning_content": "",
            "tool_calls": (),
        })()

    def health(self):
        return {"available": True, "provider": "deepseek", "model": self.default_model}


class BrokenDeepSeekProvider(FakeDeepSeekProvider):
    def chat(self, messages, **kwargs):
        fake_key = "sk" + "-" + "abcdefghijklmnopqrstuvwxyz"
        raise RuntimeError(f"bad key {fake_key}")

    def complete(self, messages, **kwargs):
        fake_key = "sk" + "-" + "abcdefghijklmnopqrstuvwxyz"
        raise RuntimeError(f"bad key {fake_key}")


class RetryableDeepSeekProvider(FakeDeepSeekProvider):
    def complete(self, messages, **kwargs):
        raise ProviderRequestError("deepseek", "timeout", retryable=True)


class FakeOllamaProvider:
    name = "ollama"

    def chat(self, messages, **kwargs):
        return "ollama answer"

    def health(self):
        return {"available": True, "provider": "ollama", "model": "qwen3:4b"}


def test_llm_router_prefers_deepseek_for_complex_analysis(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_MODE", "auto")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.DeepSeekProvider", FakeDeepSeekProvider)
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.OllamaProvider", FakeOllamaProvider)

    content, status = LLMRouter().generate_answer(
        [{"role": "user", "content": "明天电价风险大吗？"}],
        task_type="complex_analysis",
    )

    assert content == "deepseek answer"
    assert status["provider"] == "deepseek"


def test_llm_router_prefers_ollama_for_daily_chat_in_auto_mode(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_MODE", "auto")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.DeepSeekProvider", FakeDeepSeekProvider)
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.OllamaProvider", FakeOllamaProvider)

    content, status = LLMRouter().generate_answer(
        [{"role": "user", "content": "hello"}],
        task_type="daily_chat",
    )

    assert content == "ollama answer"
    assert status["provider"] == "ollama"


def test_llm_router_skips_unhealthy_ollama_for_chatbi_plans(monkeypatch):
    class UnhealthyOllamaProvider(FakeOllamaProvider):
        def health(self):
            return {"available": False, "provider": "ollama", "model": None}

    monkeypatch.setenv("LLM_ROUTER_MODE", "auto")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.DeepSeekProvider", FakeDeepSeekProvider)
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.OllamaProvider", UnhealthyOllamaProvider)

    content, status = LLMRouter().generate_answer(
        [{"role": "user", "content": "查询数据库最新天气日期"}],
        task_type="simple_data_answer",
    )

    assert content == "deepseek answer"
    assert status["provider"] == "deepseek"


def test_llm_router_auto_mode_can_fall_back_to_ollama(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_MODE", "auto")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_AUTO_PROVIDER_ORDER", "deepseek,ollama")
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.DeepSeekProvider", RetryableDeepSeekProvider)
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.OllamaProvider", FakeOllamaProvider)

    content, status = LLMRouter().generate_answer(
        [{"role": "user", "content": "复杂分析"}],
        task_type="complex_analysis",
        requested_provider="auto",
    )

    assert content == "ollama answer"
    assert status["provider"] == "ollama"
    assert status["fallback"] is True


def test_llm_router_does_not_fall_back_when_provider_is_explicit(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_MODE", "auto")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.DeepSeekProvider", BrokenDeepSeekProvider)
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.OllamaProvider", FakeOllamaProvider)

    try:
        LLMRouter().generate_answer(
            [{"role": "user", "content": "complex analysis"}],
            task_type="complex_analysis",
            requested_provider="deepseek",
        )
    except RuntimeError as exc:
        error = str(exc)
    else:
        raise AssertionError("explicit provider failure must fail closed")

    assert error.startswith("deepseek:")
    assert "ollama:" not in error
    assert ("sk" + "-***") in error


def test_sanitize_error_masks_api_key_like_values():
    fake_key = "sk" + "-" + "abcdefghijklmnopqrstuvwxyz"
    masked = sanitize_error(f"request failed: {fake_key}")
    assert ("sk" + "-***") in masked
    assert "abcdefghijklmnopqrstuvwxyz" not in masked


def test_explicit_provider_failure_is_not_wrapped_as_success(monkeypatch):
    class BrokenRouter:
        def generate_answer(self, *_args, **_kwargs):
            raise RuntimeError("provider offline")

    monkeypatch.setattr(service, "LLMRouter", BrokenRouter)
    monkeypatch.setenv("AI_ASSISTANT_LLM_ENABLED", "1")
    monkeypatch.setattr(service, "rag_enabled", lambda: False)
    monkeypatch.setattr(service, "get_conversation_state", lambda _identity: None)
    monkeypatch.setattr(service, "_execute_tools", lambda *_args, **_kwargs: [])

    try:
        service.answer_chat_accurate(
            "请从组织流程角度分析跨部门协同的三个关键约束",
            model_provider="ollama",
        )
    except service.ModelProviderUnavailableError as exc:
        assert exc.provider == "ollama"
        assert "provider offline" in exc.reason
    else:
        raise AssertionError("explicit provider failure must not return a success payload")


def test_only_selected_attachment_evidence_reaches_model_context_without_rag(monkeypatch):
    captured: dict[str, object] = {}

    class CapturingRouter:
        def generate_answer(self, messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return "附件中的项目代码是 PROJECT_CODE=ALPHA-7281。", {
                "provider": "mimo",
                "selected_provider": "mimo",
                "model": "fixture-model",
                "selected_model": "fixture-model",
                "input_tokens": 40,
                "output_tokens": 16,
                "latency_ms": 2,
                "estimated_cost": 0,
                "currency": "CNY",
                "fallback": False,
            }

    monkeypatch.setattr(service, "LLMRouter", CapturingRouter)
    monkeypatch.setenv("AI_ASSISTANT_LLM_ENABLED", "1")
    monkeypatch.setenv("AI_ATTACHMENT_MAX_TOKENS", "300")
    monkeypatch.setattr(service, "get_conversation_state", lambda _identity: None)
    monkeypatch.setattr(service, "_execute_tools", lambda *_args, **_kwargs: [])
    result = service.answer_chat_accurate(
        "所选附件中的项目代码是什么？",
        session_id="sess-alpha",
        model_provider="mimo",
        attachment_ids=["att_alpha"],
        attachment_evidence=[{
            "source_id": "attachment:att_alpha:achunk_alpha",
            "attachment_id": "att_alpha",
            "chunk_id": "achunk_alpha",
            "file_name": "alpha.txt",
            "location": {"section": "document"},
            "text": "PROJECT_CODE=ALPHA-7281",
        }],
        knowledge_scope="attachments",
    )

    prompt = str(captured["messages"])
    assert "PROJECT_CODE=ALPHA-7281" in prompt
    assert "only_selected_attachments" not in prompt
    assert captured["kwargs"]["max_tokens"] == 300
    assert result["answer"] == "附件中的项目代码是 PROJECT_CODE=ALPHA-7281。"
    assert result["attachment_grounding"] == {
        "context_applied": True,
        "knowledge_scope": "attachments",
        "selected_attachment_ids": ["att_alpha"],
        "source_ids": ["attachment:att_alpha:achunk_alpha"],
        "chunk_count": 1,
        "enterprise_kb_chunk_count": 0,
        "only_selected_attachments_mode": True,
        "max_output_tokens": 300,
    }
