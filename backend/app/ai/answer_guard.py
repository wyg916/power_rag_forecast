from __future__ import annotations

from typing import Any


BANNED_TERMS = {
    "必须买入": "建议谨慎评估买入安排",
    "必须卖出": "建议谨慎评估卖出安排",
    "保证收益": "存在不确定性",
    "稳赚": "存在不确定性",
    "确定获利": "存在不确定性",
}


def validate_answer(intent: str, answer: str, evidence: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    text = answer or ""
    for bad, replacement in BANNED_TERMS.items():
        text = text.replace(bad, replacement)

    if not evidence and intent not in {"compare_history"}:
        text = (
            "结论：当前数据不足，无法判断。\n\n"
            "依据：本次回答没有拿到可追溯的数据依据。\n\n"
            "建议：先检查数据接入、预测结果或报告生成状态，再重新提问。"
        )
    return text, evidence

