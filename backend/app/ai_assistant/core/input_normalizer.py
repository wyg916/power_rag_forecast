from __future__ import annotations

import re


def normalize_question(question: str) -> str:
    text = (question or "").strip()
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def compact_question(question: str) -> str:
    return re.sub(r"\s+", "", normalize_question(question)).lower()


def looks_like_user_text_explain(question: str) -> bool:
    text = normalize_question(question)
    compact = compact_question(text)
    explain_words = ["帮我解答", "帮我解释", "解释一下", "这是什么意思", "帮我总结", "总结一下"]
    report_signals = ["运行ID", "预测窗口", "数据窗口", "均价", "最高价", "最低价", "峰谷价差", "RMSE", "MAE"]
    return len(text) >= 120 and any(word in compact for word in explain_words) and sum(1 for s in report_signals if s.lower() in text.lower()) >= 2
