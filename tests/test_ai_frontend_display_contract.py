from __future__ import annotations

from pathlib import Path


ASSISTANT_PAGE = Path("frontend/src/pages/assistant/AssistantPage.tsx")
ASSISTANT_API = Path("frontend/src/services/assistantApi.ts")


def test_provider_display_labels_are_productized() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "deterministic: '快速回答'" in content
    assert "deepseek: '在线模型'" in content
    assert "ollama: '本地模型'" in content
    assert "fallback: '回答链路异常'" in content
    assert "普通用户默认不展示 Trace、工具调用日志和原始 JSON。" in content


def test_assistant_page_uses_messages_and_drawer_without_layout_debug_panel() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "const [messages, setMessages]" in content
    assert "assistantId = messageId('assistant')" in content
    assert "askAssistantStream(" in content
    assert "withAssistantTimeout(askAssistant(text, sessionId, options))" not in content
    assert "实时输出暂不可用，正在切换普通回答" not in content
    assert "ASSISTANT_CHAT_TIMEOUT_MS" in content
    assert "<Drawer" in content
    assert "assistant-dev-collapse" not in content
    assert "开发者信息" in content
    assert "TracePanel {...activeTrace}" in content


def test_normal_mode_does_not_create_fake_business_answer() -> None:
    api_content = ASSISTANT_API.read_text(encoding="utf-8")
    page_content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "mock_fallback" not in api_content
    assert "return api.chat(question, sessionId, options)" in api_content
    assert "exportAssistantConversation" in api_content
    assert "uploadAssistantAttachment" in api_content
    assert "getAssistantReferenceOptions" in api_content
    assert "return detail ? `请求未完成：${detail}` : '请求未完成，请稍后重试。';" in page_content
    assert "model_fallback" not in api_content


def test_assistant_page_wires_real_interactions() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "handleUploadFiles(event.target.files, 'attachment')" in content
    assert "handleUploadFiles(event.target.files, 'image')" in content
    assert "openReferencePicker" in content
    assert "setExportOpen(true)" in content
    assert "exportConversation('docx')" in content
    assert "exportConversation('pdf')" in content
    assert "assistant-context-tags" in content
