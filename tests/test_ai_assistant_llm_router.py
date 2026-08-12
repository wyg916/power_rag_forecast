from __future__ import annotations

from backend.app.ai_assistant.llm_router import LLMRouter, sanitize_error


class FakeDeepSeekProvider:
    name = "deepseek"
    default_model = "deepseek-chat"
    reasoning_model = "deepseek-reasoner"
    available = True

    def chat(self, messages, **kwargs):
        return "deepseek answer"

    def health(self):
        return {"available": True, "provider": "deepseek", "model": self.default_model}


class BrokenDeepSeekProvider(FakeDeepSeekProvider):
    def chat(self, messages, **kwargs):
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


def test_llm_router_auto_mode_can_fall_back_to_ollama(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_MODE", "auto")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr("backend.app.ai_assistant.llm_router.DeepSeekProvider", BrokenDeepSeekProvider)
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
