from __future__ import annotations

import re
from typing import Any


BAD_TERMS = {
    "必须买入": "建议谨慎评估买入安排",
    "必须卖出": "建议谨慎评估卖出安排",
    "保证收益": "存在不确定性",
    "稳赚": "存在不确定性",
    "一定上涨": "可能上涨",
    "一定下跌": "可能下跌",
    "Trace": "链路日志",
    "trace": "链路日志",
    "tool_calls": "工具调用明细",
    "workflow": "处理流程",
}

FRONTEND_SOURCE_TERMS = {
    "模拟数据": "业务数据",
    "真实数据": "业务数据",
    "测试数据": "业务数据",
    "派生数据": "计算结果",
    "Seed 数据": "业务数据",
    "seed 数据": "业务数据",
    "Demo 数据": "业务数据",
    "demo 数据": "业务数据",
    "source_type": "证据约束",
    "evidence_source_type": "证据约束",
    "historical": "历史窗口",
    "unavailable": "当前缺少可核验依据",
    "fail-closed": "停止本次结果生成",
    "derived": "计算结果",
    "simulated": "业务记录",
    "fallback": "备用流程",
}


INSUFFICIENT_DATA_TERMS = ["数据不足", "缺少数据", "没有数据", "数据缺失", "证据不足", "样本不足", "无法判断", "知识库依据不足"]
NUMERIC_CLAIM_PATTERNS = [
    r"\d+(?:\.\d+)?\s*USD/MWh",
    r"\d+(?:\.\d+)?\s*MW",
    r"(?:RMSE|MAE|MAPE)\s*(?:约|为|=|：|:)?\s*\d+(?:\.\d+)?",
    r"\d{1,2}:\d{2}",
]
STRATEGY_TERMS = ["交易建议", "策略建议", "采购", "报价", "储能", "充电", "放电", "调度", "套利"]
BOUNDARY_TERMS = ["辅助决策", "不等同于交易指令", "不等同于调度指令", "人工复核", "仅供参考"]


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _strip_unsupported_numbers_when_insufficient(text: str) -> str:
    if not _has_any(text, INSUFFICIENT_DATA_TERMS):
        return text
    cleaned = text
    for pattern in NUMERIC_CLAIM_PATTERNS:
        cleaned = re.sub(pattern, "具体数值待数据补齐后确认", cleaned, flags=re.IGNORECASE)
    if "不得编造数值" not in cleaned:
        cleaned += "\n\n限制说明：当前证据不足时，不应编造具体价格、小时段、模型误差或天气负荷数值。"
    return cleaned


def _ensure_strategy_boundary(text: str) -> str:
    if _has_any(text, STRATEGY_TERMS) and not _has_any(text, BOUNDARY_TERMS):
        return text.rstrip() + "\n\n边界说明：以上建议仅作辅助决策参考，不等同于交易指令或调度指令，执行前需要结合实时数据和人工复核。"
    return text


def guard_answer(intent: str, answer: str, evidence: list[dict[str, Any]]) -> tuple[str, str]:
    text = answer or ""
    for bad, replacement in BAD_TERMS.items():
        text = text.replace(bad, replacement)
    for engineering_term, business_term in FRONTEND_SOURCE_TERMS.items():
        text = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(engineering_term)}(?![A-Za-z0-9_])",
            business_term,
            text,
            flags=re.IGNORECASE,
        )
    text = _strip_unsupported_numbers_when_insufficient(text)
    text = _ensure_strategy_boundary(text)
    passed = True
    if intent.endswith("_latest_time") and "最新时间" not in text:
        passed = False
    if intent == "current_date_query" and "当前日期" not in text:
        passed = False
    if intent == "storage_discharge_advice" and "放电" not in text:
        passed = False
    if intent in {"low_price_reason", "high_price_reason", "risk_reason"} and not any(k in text for k in ["原因", "依据", "关键"]):
        passed = False
    if not evidence and intent not in {"general_query"}:
        passed = False
    if passed:
        return text, "passed"
    safe = text
    if "结论" not in safe:
        safe = "结论：当前系统已查询到相关数据，但回答生成不完整。\n\n" + safe
    if evidence and "数据依据" not in safe:
        safe += "\n\n数据依据：请查看下方 evidence 明细。"
    return safe, "rewritten"
