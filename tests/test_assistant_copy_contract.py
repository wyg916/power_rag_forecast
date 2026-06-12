from __future__ import annotations

from pathlib import Path


def test_assistant_page_has_question_and_answer_copy_buttons():
    source = Path("frontend/src/pages/assistant/AssistantPage.tsx").read_text(encoding="utf-8")

    assert "CopyOutlined" in source
    assert 'aria-label="复制问题"' in source
    assert 'aria-label="复制回答"' in source
    assert "navigator.clipboard.writeText" in source
