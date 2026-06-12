from __future__ import annotations

from pathlib import Path


ASSISTANT_PAGE = Path("frontend/src/pages/assistant/AssistantPage.tsx")


def test_provider_display_labels_are_productized() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "deterministic: '快速回答'" in content
    assert "deepseek: '在线模型'" in content
    assert "ollama: '本地模型'" in content
    assert "fallback: '兜底回答'" in content
    assert "providerDisplayName((assistantData as any).dataSource)" in content


def test_normal_mode_does_not_store_raw_evidence_summaries() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "developerMode && canUseDeveloperMode ? compactEvidenceItems(response.evidence_summary || []) : []" in content
    assert "developerMode && canUseDeveloperMode ? compactEvidenceItems(response.knowledge_evidence_summary || []) : []" in content
    assert "score" not in " ".join(
        line.strip()
        for line in content.splitlines()
        if "DataStateBanner" in line or "answerState.source" in line
    )


def test_answer_text_uses_structured_renderer() -> None:
    content = ASSISTANT_PAGE.read_text(encoding="utf-8")

    assert "function renderAnswerText" in content
    assert '<div className="answer-text">{renderAnswerText(currentAnswer)}</div>' in content
    assert "answer-section-line" in content
    assert "answer-bullet" in content
