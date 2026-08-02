from __future__ import annotations

from pathlib import Path


ASSISTANT_PAGE = Path("frontend/src/pages/assistant/AssistantPage.tsx")
ASSISTANT_API = Path("frontend/src/services/assistantApi.ts")


def test_provider_display_labels_are_productized() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "deterministic: '快速回答'" in content
    assert "deepseek: '在线模型'" in content
    assert "ollama: '本地模型'" in content
    assert "fallback: '降级回答'" in content
    assert "普通用户默认不展示 Trace、工具调用日志和原始 JSON。" in content


def test_assistant_page_uses_messages_and_drawer_without_layout_debug_panel() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "const [messages, setMessages]" in content
    assert "assistantId = messageId('assistant')" in content
    assert "askAssistantStream(" in content
    assert "withAssistantTimeout(askAssistant(text, sessionId, options))" in content
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
    assert "当前 AI 服务暂时不可用，未生成可用于业务决策的回答。" in page_content
    assert "本次失败不代表供需、电价或交易风险发生变化。" in page_content


def test_assistant_page_wires_real_interactions() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "handleUploadFiles(event.target.files, 'attachment')" in content
    assert "handleUploadFiles(event.target.files, 'image')" in content
    assert "openReferencePicker" in content
    assert "setExportOpen(true)" in content
    assert "exportConversation('docx')" in content
    assert "exportConversation('pdf')" in content
    assert "assistant-context-tags" in content


def test_assistant_page_consumes_grounded_claim_and_citation_contract() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "claims: Array.isArray(response.claims)" in content
    assert "citations: Array.isArray(response.citations)" in content
    assert "groundingStatus: response.grounding_status" in content
    assert "refusalReason: response.refusal_reason" in content
    assert "buildGroundedClaimLines" in content
    assert "buildCitationItems" in content
    assert "[知识依据 ${value}]" in content


def test_normal_user_evidence_view_is_business_safe_and_fail_closed() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "当前没有可验证且已发布的知识内容，未据此生成知识主张。" in content
    assert "知识证据已核验" in content
    assert "知识证据暂不可用" in content
    assert "本次回答暂无已核验知识引用" in content
    assert 'className="assistant-citation-quote"' in content
    assert "businessSafeWarning" in content
    assert "回答生成服务发生降级，本次未采用不可用模型生成的内容。" in content
    assert "来自本次受控业务查询结果" in content
    assert "trace?.refs" not in content
