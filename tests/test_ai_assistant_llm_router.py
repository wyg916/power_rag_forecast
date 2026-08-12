from __future__ import annotations

from backend.app.ai_assistant.llm_router import LLMRouter, sanitize_error


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


def test_llm_router_does_not_fall_back_for_explicit_provider(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_MODE", "auto")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.DeepSeekProvider", BrokenDeepSeekProvider)
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.OllamaProvider", FakeOllamaProvider)

    try:
        LLMRouter().generate_answer(
            [{"role": "user", "content": "复杂分析"}],
            task_type="complex_analysis",
            requested_provider="deepseek",
        )
    except RuntimeError as exc:
        assert "deepseek" in str(exc)
    else:
        raise AssertionError("explicit provider failure must not silently fall back")


def test_sanitize_error_masks_api_key_like_values():
    fake_key = "sk" + "-" + "abcdefghijklmnopqrstuvwxyz"
    masked = sanitize_error(f"request failed: {fake_key}")
    assert ("sk" + "-***") in masked
    assert "abcdefghijklmnopqrstuvwxyz" not in masked
