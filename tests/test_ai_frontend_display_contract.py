from __future__ import annotations

from pathlib import Path


ASSISTANT_PAGE = Path("frontend/src/pages/assistant/AssistantPage.tsx")
ASSISTANT_API = Path("frontend/src/services/assistantApi.ts")


def test_provider_display_labels_are_productized() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "deterministic: '快速回答'" in content
    assert "kimi: 'Kimi K2.6'" in content
    assert "mimo: 'MiMo V2.5'" in content
    assert "deepseek: 'DeepSeek V4-Flash'" in content
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


def test_ai_conversation_tier_selector_requires_explicit_premium_and_is_session_scoped() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    for label in ["标准模式", "高阶模式（明确选择）"]:
        assert label in content
    assert "const [sessionProviders, setSessionProviders]" in content
    assert "setModelProvider(sessionProviders[nextSessionId] || 'standard')" in content
    assert "requested_tier: modelProvider" in content
    assert "premium_confirmed: modelProvider === 'premium'" in content
    assert 'aria-label="AI 对话模型"' in content
    assert "model_20260620_063015" not in content


def test_normal_mode_does_not_create_fake_business_answer() -> None:
    api_content = ASSISTANT_API.read_text(encoding="utf-8")
    page_content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "mock_fallback" not in api_content
    assert "return api.chat(buildAssistantChatRequest(question" in api_content
    assert "premium_confirmed: options.premium_confirmed ?? false" in api_content
    assert "model_provider: options.model_provider || 'auto'" in api_content
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


def test_assistant_messages_use_the_app_context_api() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "App.useApp()" in content
    assert "Tag, message } from 'antd'" not in content
    assert "rowKey={(_: any, index?: number)" not in content
