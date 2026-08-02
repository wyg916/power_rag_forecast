from __future__ import annotations

import uuid
import os
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..ai.chat_memory import save_chat_exchange
from ..data_access import jsonable
from .core.answer_guard import guard_answer
from .core.answer_planner import plan_answer
from .core.context_resolver import resolve_followup
from .core.input_normalizer import normalize_question
from .core.intent_router import route_intent
from .core.tool_router import tools_for_intent
from .core.trace_manager import TraceManager
from .context_pack_builder import build_context_pack
from .expert_answer_planner import normalize_answer_style, plan_expert_answer
from .llm_router import LLMRouter, sanitize_error
from .memory.conversation_state import get_conversation_state, save_conversation_state
from .prompts import build_expert_messages
from .schemas import ConversationState, IntentDecision, ToolResult
from ..services.core_data_sync import save_ai_trace_record
from ..services.rag_service import rag_enabled, rag_search
from .templates.deterministic_answers import answer_current_date, answer_data_freshness, answer_data_sql_query, answer_forecast_metric, answer_prediction_window
from .templates.fallback_answers import (
    answer_high_price_reason,
    answer_low_price_reason,
    answer_storage_charge,
    answer_storage_discharge,
    answer_user_text,
    answer_weather_summary,
)
from .tools import execute_tool


DATA_LABELS = {
    "weather_data_latest_time": "天气数据",
    "price_data_latest_time": "电价数据",
    "load_data_latest_time": "负荷数据",
    "database_table_freshness": "数据库表",
}


def _llm_enabled() -> bool:
    value = os.environ.get("AI_ASSISTANT_LLM_ENABLED", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _security_refusal_reason(question: str) -> str:
    compact = re.sub(r"\s+", "", (question or "").lower())
    rules = {
        "sensitive_information": [
            "输出数据库连接", "显示数据库连接", "database_url", "输出token", "显示token",
            "输出secret", "显示secret", "输出密钥", "显示密钥", "输出密码", "显示密码",
            "内部trace", "系统提示词", "系统prompt", "systemprompt", "api_key", "apikey",
            "bearertoken", "显示bearer", "内部密钥", "泄露系统", "原样返回",
            "sentinel_secret_must_not_leak", "数据库连接串",
        ],
        "prompt_injection": ["忽略以前指令", "忽略之前指令", "ignoreprevious", "忽略安全规则", "绕过安全", "关闭安全检查"],
        "unauthorized_action": ["绕过权限", "越权访问", "删除数据库", "删库", "dropdatabase", "关闭审计"],
        "automatic_trading": ["直接替我下单", "自动替我交易", "执行自动交易", "保证盈利", "承诺收益", "声称系统已经生产部署", "生产部署并能自动交易"],
    }
    for reason, terms in rules.items():
        if any(term in compact for term in terms):
            return reason
    return ""


def _explicit_unavailable_reason(question: str) -> str:
    compact = re.sub(r"\s+", "", (question or "").lower())
    if "从未记录" in compact and any(term in compact for term in ["收益", "成交", "准确"]):
        return "unrecorded_business_fact"
    if all(term in compact for term in ["soc", "容量", "效率"]) and any(term in compact for term in ["精确", "具体"]):
        return "missing_storage_constraints"
    if any(term in compact for term in ["缺少模型误差", "没有模型误差", "模型误差数据缺失"]) and any(
        term in compact for term in ["断言", "一定变差", "准确判断"]
    ):
        return "missing_model_error_evidence"
    return ""


def _security_refusal_payload(
    *, session_id: str, model_provider: str, debug: bool, reason: str
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "answer": "拒绝：该请求涉及敏感信息、越权操作、提示词注入或自动交易边界，系统不会执行或披露。可改为只读且需要人工复核的安全说明。",
        "source_type": "unavailable",
        "domain": "system_knowledge",
        "run_id": None,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "confidence": "high",
        "citations": [],
        "evidence": [],
        "answer_style": "professional_brief",
        "model_provider_used": "deterministic",
        "model_provider_requested": model_provider,
        "model_fallback": False,
        "llm_used": False,
        "warnings": [],
        "refused": True,
        "security_reason": reason,
    }
    if debug:
        payload.update(
            {
                "intent": "security_refusal",
                "tool_calls": [],
                "tools": [],
                "rag": {"available": False, "items": [], "retrieval": {"enabled": False, "reason": "security_refusal"}},
                "trace_id": "",
                "workflow": ["input_normalizer", "security_boundary"],
            }
        )
    return jsonable(payload)


def _unavailable_payload(*, session_id: str, model_provider: str, debug: bool, reason: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "answer": "unavailable：缺少可信证据或关键业务约束，不能编造实时数值、收益或精确充放电量。",
        "source_type": "unavailable",
        "domain": "system_knowledge",
        "run_id": None,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "confidence": "none",
        "citations": [],
        "evidence": [],
        "answer_style": "professional_brief",
        "model_provider_used": "deterministic",
        "model_provider_requested": model_provider,
        "model_fallback": False,
        "llm_used": False,
        "warnings": [],
        "unavailable_reason": reason,
    }
    if debug:
        payload.update({"intent": "explicit_unavailable", "tool_calls": [], "tools": [], "rag": {"available": False, "items": [], "retrieval": {"enabled": False, "reason": reason}}, "trace_id": "", "workflow": ["input_normalizer", "unavailable_boundary"]})
    return jsonable(payload)


RAG_INTENTS = {
    "forecast_max_price",
    "forecast_min_price",
    "forecast_avg_price",
    "forecast_spread",
    "forecast_risk_hours",
    "low_price_reason",
    "high_price_reason",
    "risk_reason",
    "storage_discharge_advice",
    "storage_charge_advice",
    "storage_spread_analysis",
    "trading_risk_summary",
    "weather_summary",
    "weather_impact_on_price",
    "model_error_status",
    "model_retrain_suggestion",
    "report_summary",
    "knowledge_search",
    "tariff_query",
    "station_tariff_check",
    "tariff_policy_search",
    "market_power_price_query",
    "southern_grid_tax_query",
}


PROFESSIONAL_RAG_TERMS = [
    "电价",
    "现货",
    "日前",
    "实时",
    "lmp",
    "pjm",
    "dom",
    "dominion",
    "绿证",
    "绿色电力",
    "代理购电",
    "峰谷",
    "分时",
    "电力市场",
    "交易规则",
    "实施细则",
    "出清",
    "尖峰",
    "高价风险",
    "低价机会",
    "负荷",
    "天气",
    "价格",
    "预测",
    "高价",
    "低价",
    "晚高峰",
    "价格高",
    "价格低",
    "rmse",
    "mae",
    "模型误差",
    "预测误差",
    "误差变大",
    "模型漂移",
    "模型退化",
    "模型训练",
    "训练流程",
    "生产切换",
    "真实值回填",
    "回填不足",
    "样本不足",
    "数据不足",
    "缺少数据",
    "没有数据",
    "数据缺失",
    "证据不足",
    "无法判断",
    "天气新鲜度",
    "天气更新时间",
    "天气过期",
    "预测区间",
    "特征工程",
    "新能源",
    "光伏",
    "风电",
    "储能",
    "项目申报",
    "售电",
    "交易策略",
    "电网",
    "市场机制",
    "政策",
    "规则",
    "合约敞口",
    "报价",
    "采购",
    "套利",
    "soc",
    "容量约束",
    "功率约束",
    "循环次数",
    "模型切换",
    "模型回退",
    "deepseek",
    "ollama",
    "本地模型",
    "在线模型",
    "fallback",
    "辅助决策",
    "负价",
]


SYSTEM_USAGE_RAG_TERMS = [
    "这个系统",
    "系统是做什么",
    "项目是做什么",
    "ai助手",
    "助手能帮",
    "开发者模式",
    "普通模式",
    "工具调用",
    "预测中心",
    "策略中心",
    "模型运维",
    "预测数据",
    "没有预测数据",
]


DAILY_CHAT_RAG_SKIP_TERMS = [
    "今天星期几",
    "今天周几",
    "现在星期几",
    "现在周几",
    "星期几",
    "周几",
    "你是谁",
    "你好",
    "谢谢",
    "帮我写一句话",
    "讲个笑话",
]


FAST_PATH_INTENTS = {
    "greeting",
    "thanks",
    "identity",
    "capability",
    "time",
    "weekday",
    "brief_answer_request",
    "plain_language_intro",
    "multi_daily_chat",
    "current_date_query",
}

DIRECT_DATA_INTENTS = {
    "weather_data_latest_time",
    "price_data_latest_time",
    "load_data_latest_time",
    "database_table_freshness",
    "data_sql_query",
}

BRIEF_ANSWER_MARKERS = [
    "一句话回答",
    "一句话说说",
    "简短回答",
    "简洁回答",
    "用一句话",
    "一句话",
]

CAPABILITY_PATTERNS = [
    "你能做什么",
    "你可以做什么",
    "你可以帮我分析什么",
    "你可以帮我分析哪些内容",
    "你能帮我分析什么",
    "你能帮我看什么",
    "你会分析哪些内容",
    "这个助手有什么用",
    "助手有什么用",
    "能做什么",
    "可以做什么",
]

IDENTITY_PATTERNS = ["你是谁", "你是什么助手", "你是什么", "介绍一下你自己"]
GREETING_PATTERNS = ["你好", "您好", "早上好", "下午好", "晚上好", "hello", "hi"]
THANKS_PATTERNS = ["谢谢", "感谢", "辛苦了", "不客气"]
TIME_PATTERNS = ["现在几点", "几点了", "当前时间", "现在时间"]
WEEKDAY_PATTERNS = ["今天星期几", "今天周几", "星期几", "周几", "当前日期", "今天几号", "今天是几号", "今天日期", "现在日期"]
PLAIN_LANGUAGE_PATTERNS = ["通俗话", "通俗地", "简单说", "简单解释", "解释一下你是什么助手"]


def _rag_top_k() -> int:
    try:
        return max(1, min(int(os.environ.get("RAG_TOP_K", "5") or "5"), 10))
    except Exception:
        return 5


def _compact_match_text(value: str) -> str:
    return "".join((value or "").lower().split())


def _matched_terms(question: str, terms: list[str]) -> list[str]:
    q = _compact_match_text(question)
    return [term for term in terms if _compact_match_text(term) and _compact_match_text(term) in q]


def _contains_any_compact(question: str, terms: list[str]) -> bool:
    q = _compact_match_text(question)
    for term in terms:
        compact_term = _compact_match_text(term)
        if not compact_term:
            continue
        if compact_term.isascii() and compact_term.isalnum():
            if re.search(rf"(?<![a-z0-9]){re.escape(compact_term)}(?![a-z0-9])", q):
                return True
        elif compact_term in q:
            return True
    return False


def _rag_domain_hint(question: str) -> str:
    compact = _compact_match_text(question)
    if any(term in compact for term in ["source_type", "historical", "unavailable", "fallback", "seed", "demo", "generated_at", "effective_at", "过期文档", "知识文档", "系统功能", "开发者模式"]):
        return "system_knowledge"
    if any(term in compact for term in ["这个系统", "预测中心", "策略中心", "知识库中心", "ai助手", "工具调用", "citation", "run_id", "可追溯", "系统边界", "没有预测数据", "查询接口", "candidate", "active", "事实源"]):
        return "system_knowledge"
    if any(term in compact for term in ["pjm", "lmp", "dom", "日前市场", "实时市场", "节点电价", "负电价"]):
        return "electricity_market"
    if any(term in compact for term in ["报告中心", "报告"]):
        return "report"
    if any(term in compact for term in ["交易", "采购", "储能", "报价", "敞口", "售电公司"]):
        return "trading_strategy"
    if any(term in compact for term in ["新能源", "出力", "光伏", "风电"]):
        return "renewable_policy"
    if any(term in compact for term in ["数据质量", "数据新鲜度", "数据不新鲜", "缺失数据"]):
        return "data_quality"
    if any(term in compact for term in ["模型", "预测", "mae", "rmse", "尖峰", "风险", "电价", "价格", "价差", "高价", "低价", "异常", "负荷", "天气"]):
        return "price_forecast"
    return ""


def _weekday_label(value: datetime) -> str:
    return ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][value.weekday()]


def _now_text() -> str:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return f"现在是 {now:%Y-%m-%d %H:%M}，{_weekday_label(now)}。"


def _current_date_text() -> str:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return f"当前日期：{now:%Y-%m-%d}；现在是 {now:%Y-%m-%d %H:%M}，{_weekday_label(now)}。"


def _daily_fast_path_flags(question: str, intent: str) -> dict[str, bool]:
    q = _compact_match_text(question)
    flags = {
        "brief": _contains_any_compact(question, BRIEF_ANSWER_MARKERS),
        "greeting": _contains_any_compact(question, GREETING_PATTERNS),
        "thanks": _contains_any_compact(question, THANKS_PATTERNS),
        "identity": _contains_any_compact(question, IDENTITY_PATTERNS),
        "capability": _contains_any_compact(question, CAPABILITY_PATTERNS),
        "plain": _contains_any_compact(question, PLAIN_LANGUAGE_PATTERNS),
        "time": _contains_any_compact(question, TIME_PATTERNS),
        "weekday": _contains_any_compact(question, WEEKDAY_PATTERNS),
    }
    legacy_mojibake_date = any(marker in q for marker in ["浠婂ぉ", "鐜板湪", "鏄熸湡", "鍛ㄥ嚑"])
    if intent == "current_date_query" and (flags["time"] or flags["weekday"] or not legacy_mojibake_date):
        if not flags["weekday"]:
            flags["time"] = True
    if intent in {"greeting", "thanks", "identity", "capability", "time", "weekday", "plain_language_intro"}:
        key = "plain" if intent == "plain_language_intro" else intent
        flags[key] = True
    # "一句话回答：你能做什么" often contains punctuation between modifier and question.
    if flags["brief"] and any(pattern in q for pattern in ["能做什么", "可以做什么", "分析什么", "分析哪些内容"]):
        flags["capability"] = True
    if flags["plain"] and any(term in q for term in ["你是什么助手", "你是什么", "介绍"]):
        flags["identity"] = True
    return flags


def _daily_fast_path_answer(question: str, intent: str) -> tuple[str, dict[str, bool], str] | None:
    flags = _daily_fast_path_flags(question, intent)
    active = {key for key, value in flags.items() if value and key != "brief"}
    if not active and flags["brief"]:
        return "可以，我会尽量用一句话回答。", flags, "brief_answer_request"
    if not active:
        return None

    if flags["capability"] and len(active) == 1:
        if flags["brief"]:
            return "我能帮你分析电价预测、负荷天气、尖峰风险、模型误差和交易策略。", flags, "capability"
        if flags["plain"]:
            return "你可以把我当成一个懂电价预测和售电交易的分析助手，帮你看价格风险、负荷天气影响、模型误差和交易关注点。", flags, "plain_language_intro"
        return "我可以帮你分析电价走势、分时电价预测、负荷和天气影响、尖峰风险、模型误差、储能策略、交易建议和报告内容。", flags, "capability"

    if flags["identity"] and len(active) == 1:
        if flags["plain"]:
            return "你可以把我当成一个懂电价预测和售电交易的分析助手，帮你看价格风险、负荷天气影响、模型误差和交易关注点。", flags, "plain_language_intro"
        return "我是面向售电交易和电价预测场景的智能分析助手，可以结合预测数据、知识库和模型结果，辅助你分析价格风险和运营策略。", flags, "identity"

    if flags["plain"] and flags["identity"] and active <= {"plain", "identity"}:
        return "你可以把我当成一个懂电价预测和售电交易的分析助手，帮你看价格风险、负荷天气影响、模型误差和交易关注点。", flags, "plain_language_intro"

    if active <= {"time", "weekday"}:
        answer = _current_date_text() if flags["weekday"] and not flags["time"] else _now_text()
        return answer, flags, "current_date_query"
    if active == {"greeting"}:
        return "你好，我在。你可以直接问我电价预测、尖峰风险、负荷天气或交易策略。", flags, "greeting"
    if active == {"thanks"}:
        return "不客气。", flags, "thanks"

    pieces: list[str] = []
    if flags["greeting"]:
        pieces.append("你好")
    if flags["identity"] or flags["plain"]:
        pieces.append("我是一个面向售电交易和电价预测的智能分析助手")
    if flags["time"] or flags["weekday"]:
        pieces.append(_now_text().rstrip("。"))
    if flags["capability"] or flags["identity"] or flags["plain"]:
        if flags["brief"]:
            pieces.append("我能帮你分析电价预测、负荷天气、尖峰风险、模型误差和交易策略")
        else:
            pieces.append("我可以帮你分析电价走势、分时预测、负荷天气影响、尖峰风险、模型误差、储能策略、交易建议和报告内容")
    if flags["thanks"]:
        pieces.append("感谢你的使用")
    if not pieces:
        return None
    answer = "；".join(dict.fromkeys(pieces)).rstrip("。") + "。"
    return answer, flags, "multi_daily_chat" if len(active) > 1 else next(iter(active))


def _daily_fast_path_payload(
    question: str,
    decision: IntentDecision,
    session_id: str,
    answer_style: str,
    model_provider: str,
    debug: bool,
    trace: TraceManager,
    timings_ms: dict[str, float],
    total_started: float,
) -> dict[str, Any] | None:
    result = _daily_fast_path_answer(question, decision.intent)
    if not result:
        return None
    answer, flags, fast_intent = result
    decision.intent = fast_intent
    timings_ms["tool_executor_ms"] = 0.0
    timings_ms["rag_trigger_ms"] = 0.0
    timings_ms["rag_total_ms"] = 0.0
    timings_ms["context_pack_ms"] = 0.0
    timings_ms["llm_generate_ms"] = 0.0
    timings_ms["answer_guard_ms"] = 0.0
    timings_ms["total_ms"] = _timing_ms(total_started)
    trace.step("daily_fast_path", intent=fast_intent, flags={key: value for key, value in flags.items() if value})
    trace_payload = trace.finish(
        intent=fast_intent,
        intent_confidence=max(float(decision.confidence or 0.0), 0.95),
        llm_used=False,
        answer_mode="daily_fast_path",
        guard_result="passed",
    )
    payload: dict[str, Any] = {
        "session_id": session_id,
        "answer": answer,
        "answer_style": normalize_answer_style(answer_style),
        "model_provider_used": "deterministic",
        "model_provider_requested": model_provider,
        "model_fallback": False,
        "llm_used": False,
        "data_used": {
            "prediction": False,
            "weather": False,
            "load": False,
            "history": False,
            "model": False,
            "report": False,
            "storage": False,
            "data_freshness": False,
            "user_text": False,
            "tariff": False,
            "knowledge": False,
        },
        "evidence_summary": [],
        "knowledge_evidence_summary": [],
        "warnings": [],
        "risk_level": "",
        "focus_periods": [],
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(sep=" ", timespec="seconds"),
    }
    if debug:
        debug_tools = []
        debug_tool_calls = []
        if fast_intent == "current_date_query":
            debug_tools = [{"name": "get_current_date_context", "input": {}, "success": True}]
            debug_tool_calls = [{"tool_name": "get_current_date_context", "input": {}, "success": True, "output": {"fast_path": True}, "error_message": ""}]
        payload.update(
            {
                "intent": fast_intent,
                "confidence": max(float(decision.confidence or 0.0), 0.95),
                "entities": {"daily_fast_path": {key: value for key, value in flags.items() if value}},
                "answer_mode": "daily_fast_path",
                "task_type": "daily_chat",
                "model_used": False,
                "model_error": "",
                "local_model": {"provider": "deterministic", "model": "daily_fast_path", "fallback": False},
                "tools": debug_tools,
                "tool_calls": debug_tool_calls,
                "evidence": [],
                "rag": {"available": False, "items": [], "retrieval": {"enabled": False, "reason": "daily_fast_path"}},
                "rag_trigger": {"reason": "daily_fast_path", "matched_terms": []},
                "timings_ms": timings_ms,
                "trace": trace_payload,
                "agent_trace": trace_payload.get("steps", []),
                "trace_id": trace.trace_id,
                "related_actions": [],
                "suggestions": [],
                "complexity": "simple",
                "workflow": ["input_normalizer", "context_resolver", "intent_router", "daily_fast_path"],
            }
        )
    return jsonable(payload)


def _rag_trigger_decision(intent: str, task_type: str, question: str) -> tuple[bool, dict[str, Any]]:
    info: dict[str, Any] = {"reason": "", "matched_terms": []}
    if not rag_enabled():
        info["reason"] = "rag_disabled"
        return False, info
    if intent in FAST_PATH_INTENTS or intent in DIRECT_DATA_INTENTS:
        info["reason"] = "daily_or_deterministic_skipped"
        return False, info

    professional_terms = _matched_terms(question, PROFESSIONAL_RAG_TERMS)
    system_terms = _matched_terms(question, SYSTEM_USAGE_RAG_TERMS)
    daily_terms = _matched_terms(question, DAILY_CHAT_RAG_SKIP_TERMS)

    if daily_terms and not professional_terms and not system_terms:
        info.update({"reason": "daily_chat_skipped", "matched_terms": daily_terms})
        return False, info
    if professional_terms:
        info.update({"reason": "professional_domain_terms", "matched_terms": professional_terms[:12]})
        return True, info
    if system_terms:
        info.update({"reason": "system_usage_terms", "matched_terms": system_terms[:12]})
        return True, info
    if intent in {"general_query", "prediction_window_query"} or task_type == "daily_chat":
        info["reason"] = "intent_or_task_type_skipped"
        return False, info
    if intent in RAG_INTENTS:
        info["reason"] = "intent_matched"
        return True, info
    if task_type in {"complex_analysis", "business_answer"}:
        info["reason"] = "task_type_matched"
        return True, info
    info["reason"] = "intent_or_task_type_skipped"
    return False, info


def _should_use_rag(intent: str, task_type: str, question: str = "") -> bool:
    return _rag_trigger_decision(intent, task_type, question)[0]


def _should_use_llm(intent: str) -> bool:
    return intent not in FAST_PATH_INTENTS and intent not in DIRECT_DATA_INTENTS


def _timing_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _daily_llm_enabled() -> bool:
    value = os.environ.get("AI_ASSISTANT_DAILY_LLM_ENABLED", "0").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _should_skip_llm_for_daily_chat(intent: str, task_type: str, question: str) -> bool:
    if _daily_llm_enabled():
        return False
    if intent in FAST_PATH_INTENTS:
        return True
    if intent != "general_query" and task_type != "daily_chat":
        return False
    daily_terms = _matched_terms(question, DAILY_CHAT_RAG_SKIP_TERMS)
    if not daily_terms:
        return False
    return not _matched_terms(question, PROFESSIONAL_RAG_TERMS) and not _matched_terms(question, SYSTEM_USAGE_RAG_TERMS)


def _rag_evidence(rag_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **citation,
            "source_type": rag_result.get("source_type") or "unavailable",
            "domain": rag_result.get("domain") or "",
            "tool": "rag_hybrid_search",
        }
        for citation in (rag_result or {}).get("citations", [])[:8]
    ]


def _safe_money(value: Any) -> str:
    try:
        return f"{float(value):.2f} USD/MWh"
    except Exception:
        return "-"


def _preserve_required_business_terms(intent: str, answer: str, draft_answer: str) -> str:
    required_by_intent = {
        "storage_discharge_advice": ["低价充电参考", "峰谷价差"],
        "storage_spread_analysis": ["低价充电参考", "峰谷价差"],
        "storage_charge_advice": ["高价放电参考", "峰谷价差"],
        "user_provided_text_explain": ["预测窗口", "最高价", "最低价", "峰谷价差"],
    }
    missing = [term for term in required_by_intent.get(intent, []) if term not in answer]
    if not missing:
        return answer
    return answer.rstrip() + "\n\n补充工具依据：\n" + draft_answer.strip()


def _looks_like_reasoning_leak(answer: str) -> bool:
    head = answer.strip()[:500]
    if "</think>" in head.lower() or "<think>" in head.lower():
        return True
    markers = ["首先，用户", "用户的问题是", "我需要", "关键点", "证据分析", "作为售电交易AI助手"]
    return any(marker in head for marker in markers)


def _tool_args(name: str, decision: IntentDecision, run_id: str, question: str) -> dict[str, Any]:
    args: dict[str, Any] = {"run_id": run_id, **decision.entities}
    if name == "get_data_freshness":
        default_domain = "master_table" if decision.intent == "database_table_freshness" else "weather"
        args["domain"] = decision.entities.get("domain") or default_domain
    if name in {"explain_low_price_hour", "explain_high_price_hour"}:
        args["target_time"] = decision.entities.get("target_time")
        args["hour"] = decision.entities.get("hour")
    if name == "explain_user_provided_text":
        args["text"] = decision.entities.get("text") or question
    if name in {
        "query_pv_tariff",
        "check_station_tariff",
        "search_tariff_policy",
        "query_market_power_price",
        "query_southern_grid_tax_rule",
        "search_business_knowledge",
        "query_business_data",
    }:
        args["question"] = question
        args["keyword"] = decision.entities.get("keyword") or question
        if name == "search_business_knowledge":
            args["domain"] = _rag_domain_hint(question)
    return args


def _execute_tools(decision: IntentDecision, run_id: str, question: str) -> list[ToolResult]:
    results: list[ToolResult] = []
    for name in tools_for_intent(decision.intent):
        args = _tool_args(name, decision, run_id, question)
        try:
            output = execute_tool(name, **args)
            success = bool(output.get("available", True)) and not bool(output.get("empty"))
            results.append(ToolResult(name, args, output, success))
        except Exception as exc:
            results.append(ToolResult(name, args, {"tool": name, "available": False, "message": str(exc)}, False, str(exc)))
    return results


def _first(results: list[ToolResult], name: str | None = None) -> dict[str, Any]:
    for result in results:
        if name is None or result.name == name:
            return result.output
    return {}


def _evidence(results: list[ToolResult]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for result in results:
        for item in result.output.get("evidence") or []:
            evidence.append(dict(item, tool=result.name))
        if result.output.get("evidence"):
            continue
        if result.name == "get_high_risk_hours" and result.output.get("items"):
            evidence.append({"source": "result_forward_24h_formal", "fields": ["datetime", "predicted_price", "risk_level"], "tool": result.name})
        elif result.name == "get_report_summary" and result.output.get("report_id"):
            evidence.append({"source": "ai_report_status", "report_id": result.output.get("report_id"), "tool": result.name})
        elif result.name == "get_model_error_summary":
            evidence.append({"source": "prediction_tracking", "operation": "model_error_summary", "tool": result.name})
    return evidence


def _data_used(results: list[ToolResult]) -> dict[str, bool]:
    used = {
        "prediction": False,
        "weather": False,
        "load": False,
        "history": False,
        "model": False,
        "report": False,
        "storage": False,
        "data_freshness": False,
        "data_query": False,
        "user_text": False,
        "tariff": False,
        "knowledge": False,
    }
    for result in results:
        name = result.name
        if name in {"get_forecast_metrics", "get_high_risk_hours", "explain_low_price_hour", "explain_high_price_hour"}:
            used["prediction"] = True
        if name == "get_weather_summary":
            used["weather"] = True
        if name == "get_data_freshness":
            used["data_freshness"] = True
            domain = result.output.get("domain")
            if domain == "weather":
                used["weather"] = True
            if domain in {"load", "forecast_load"}:
                used["load"] = True
        if name == "query_business_data":
            used["data_query"] = True
            dataset_id = str(result.output.get("dataset_id") or "")
            if "weather" in dataset_id:
                used["weather"] = True
            if "load" in dataset_id:
                used["load"] = True
            if "forecast" in dataset_id:
                used["prediction"] = True
        if name in {"get_storage_discharge_windows", "get_storage_charge_windows"}:
            used["storage"] = True
            used["prediction"] = True
        if name == "get_model_error_summary":
            used["model"] = True
        if name == "get_report_summary":
            used["report"] = True
        if name == "explain_user_provided_text":
            used["user_text"] = True
        if name in {"query_pv_tariff", "check_station_tariff", "search_tariff_policy", "query_market_power_price", "query_southern_grid_tax_rule"}:
            used["tariff"] = True
        if name == "search_business_knowledge":
            used["knowledge"] = True
    return used


def _evidence_summary(evidence: list[dict[str, Any]]) -> list[str]:
    summary: list[str] = []
    for item in evidence[:8]:
        source = item.get("source") or item.get("title") or item.get("chunk_id") or "系统数据"
        details = []
        if item.get("time"):
            details.append(str(item.get("time")))
        if item.get("fields"):
            details.append(",".join(str(value) for value in item.get("fields") or []))
        if item.get("score") is not None:
            details.append(f"score={item.get('score')}")
        summary.append(f"{source}" + (f"（{'；'.join(details)}）" if details else ""))
    return summary


def _needs_weather_attribution_boundary(question: str) -> bool:
    return _contains_any_compact(question, ["天气没更新", "天气未更新", "天气数据没更新", "天气过期", "晚高峰", "归因", "因为天气"])


def _storage_boundary_note(question: str) -> str:
    if not _contains_any_compact(question, ["储能", "soc", "容量", "充放电", "充电量", "放电量"]):
        return ""
    return (
        "\n\n储能边界：如果缺少储能 SOC、可用容量、额定功率、效率和合同约束，"
        "只能给方向性建议，不能给具体充放电量或调度指令。相关建议仅作辅助决策参考，不等同于交易或调度指令。"
    )


LEAK_LINE_PREFIXES = ("intent", "workflow", "tools", "tool_calls", "trace", "trace id", "trace_id", "agent_trace")


def _split_sentences(text: str, limit: int = 6) -> list[str]:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*", compact)
    return [part.strip() for part in parts if part.strip()][:limit]


def sanitize_answer_for_display(answer: str) -> str:
    text = str(answer or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = text.replace("```", "").replace("`", "")
    cleaned_lines: list[str] = []
    blank = False
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        line = re.sub(r"^#{1,6}\s*", "", line)
        if re.fullmatch(r"[-*_]{3,}", line):
            continue
        lower = line.lower().strip(" ：:")
        if any(lower.startswith(prefix) for prefix in LEAK_LINE_PREFIXES):
            continue
        if "chunk_id" in lower or "top-k" in lower:
            continue
        line = re.sub(r"[A-Za-z]:[\\/][^\n，。；;）)]+", "", line)
        line = re.sub(r"\(?\s*score\s*=\s*[-+]?\d+(?:\.\d+)?\s*\)?", "", line, flags=re.IGNORECASE)
        line = re.sub(r"Trace\s*ID\s*[:：]?\s*\S+", "", line, flags=re.IGNORECASE)
        line = re.sub(r"\s{2,}", " ", line).strip()
        if not line:
            if not blank and cleaned_lines:
                cleaned_lines.append("")
            blank = True
            continue
        cleaned_lines.append(line)
        blank = False
    return "\n".join(cleaned_lines).strip()


def _has_any_heading(text: str, headings: list[str]) -> bool:
    return any(re.search(rf"(^|\n)\s*{re.escape(heading)}\s*[:：]?", text) for heading in headings)


def apply_answer_style_contract(answer: str, answer_style: str, intent: str, question: str) -> str:
    text = sanitize_answer_for_display(answer)
    style = normalize_answer_style(answer_style)
    if intent in FAST_PATH_INTENTS or not text:
        return text
    if style == "business_advice":
        if _has_any_heading(text, ["核心判断", "建议动作", "重点监控指标", "边界说明"]):
            return text
        sentences = _split_sentences(text, 6)
        judgment = sentences[0] if sentences else text
        actions = sentences[1:4] or ["复核预测价格、负荷、天气扰动和现货暴露比例。"]
        return (
            f"核心判断：\n{judgment}\n\n"
            "建议动作：\n"
            + "\n".join(f"- {item}" for item in actions)
            + "\n\n重点监控指标：\n- 高峰小时价格\n- 峰谷价差\n- 负荷预测\n- 天气扰动\n- 实时市场偏差\n\n"
            "边界说明：\n以上建议仅作为辅助决策参考，不等同于交易指令或调度指令。"
        )
    if style == "plain_language":
        if "通俗来说" in text or len(text.split("\n")) <= 4:
            return text
        sentences = _split_sentences(text, 7)
        return "通俗来说，" + "\n".join(sentences)
    if style == "report_style":
        if _has_any_heading(text, ["摘要", "风险判断", "原因分析", "建议动作"]):
            return text
        sentences = _split_sentences(text, 8)
        return (
            f"摘要：\n{sentences[0] if sentences else text}\n\n"
            "风险判断：\n- 重点关注高峰时段价格波动和风险等级变化。\n\n"
            "原因分析：\n"
            + "\n".join(f"- {item}" for item in (sentences[1:4] or ["需要结合负荷、天气、供需和模型误差综合判断。"]))
            + "\n\n建议动作：\n- 复核关键小时预测。\n- 检查合同覆盖和现货暴露比例。\n- 必要时更新风险预案。"
        )
    if style == "professional_deep":
        if _has_any_heading(text, ["结论", "关键原因", "建议关注", "风险边界"]):
            return text
        sentences = _split_sentences(text, 8)
        return (
            f"结论：\n{sentences[0] if sentences else text}\n\n"
            "关键原因：\n"
            + "\n".join(f"{idx}. {item}" for idx, item in enumerate(sentences[1:5] or ["需要结合负荷、天气、供需和模型误差判断。"], 1))
            + "\n\n建议关注：\n- 重点时段\n- 关键指标\n- 后续检查项\n\n"
            "风险边界：\n当前判断依赖已有事实包和知识库证据，数据不足时需要人工复核。"
        )
    if style == "professional_brief":
        if _has_any_heading(text, ["结论", "主要原因", "建议"]):
            return text
        sentences = _split_sentences(text, 5)
        return (
            f"结论：{sentences[0] if sentences else text}\n\n"
            "主要原因：\n"
            + "\n".join(f"- {item}" for item in (sentences[1:4] or ["需要结合负荷、天气、供需和预测结果综合判断。"]))
            + "\n\n建议：重点关注关键小时、预测价格和风险等级变化。"
        )
    return text


def _build_answer(decision: IntentDecision, results: list[ToolResult]) -> str:
    intent = decision.intent
    first = _first(results)
    if intent == "current_date_query":
        return answer_current_date(first)
    if intent == "prediction_window_query":
        return answer_prediction_window(first)
    if intent in DATA_LABELS:
        if intent == "weather_data_latest_time" and _needs_weather_attribution_boundary(decision.normalized_question):
            return (
                "结论：当前天气数据未更新或证据不足时，不能直接把晚高峰电价偏高归因于天气。\n\n"
                "依据边界：天气通常通过负荷需求、制冷/采暖需求、新能源出力和供需紧张程度影响电价；"
                "但需要先确认天气数据更新时间、预测窗口、覆盖区域和小时粒度。\n\n"
                "建议：先检查天气源 last_update、预测窗口、负荷预测和价格预测是否同步更新，再判断天气是否是晚高峰风险的主要驱动。"
            )
        return answer_data_freshness(first, DATA_LABELS[intent])
    if intent == "data_sql_query":
        return answer_data_sql_query(first)
    if intent in {"forecast_max_price", "forecast_min_price", "forecast_avg_price", "forecast_spread"}:
        return answer_forecast_metric(first, intent)
    if intent == "storage_discharge_advice" or intent == "storage_spread_analysis":
        return answer_storage_discharge(first)
    if intent == "storage_charge_advice":
        return answer_storage_charge(first)
    if intent == "low_price_reason":
        return answer_low_price_reason(first)
    if intent in {"high_price_reason", "risk_reason"}:
        return answer_high_price_reason(first)
    if intent == "user_provided_text_explain":
        return answer_user_text(first)
    if intent == "weather_summary":
        return answer_weather_summary(first)
    if intent == "weather_impact_on_price":
        weather = _first(results, "get_weather_summary")
        forecast = _first(results, "get_forecast_metrics")
        return (
            f"结论：天气会通过负荷变化影响电价，但当前回答只基于系统已有天气和预测数据。\n\n"
            f"天气依据：{weather.get('city') or '-'} 气温约 {weather.get('min_temperature')} 至 {weather.get('max_temperature')} 摄氏度。\n\n"
            f"电价依据：预测均价约 {forecast.get('avg_price')} USD/MWh，最高价约 {forecast.get('max_price')} USD/MWh。\n\n"
            "业务解释：高温、低温或降雨等因素可能改变用电负荷，进而影响高峰时段价格，需要结合负荷预测一起判断。"
        )
    if intent == "forecast_risk_hours":
        items = first.get("items") or []
        rows = [f"{idx}. {item.get('hour')}，风险 {item.get('risk_level')}，预测价 {item.get('predicted_price')} USD/MWh" for idx, item in enumerate(items[:6], 1)]
        return "结论：当前电价可能偏高的重点风险时段如下。\n\n" + ("\n".join(rows) if rows else "暂无明确高风险时段。") + "\n\n建议：这些小时应优先复核售电敞口和实时市场变化；预测结果不能直接作为交易指令。"
    if intent == "trading_risk_summary":
        storage = _first(results, "get_storage_discharge_windows")
        risk = _first(results, "get_high_risk_hours")
        weather = _first(results, "get_weather_summary")
        model = _first(results, "get_model_error_summary")
        discharge = storage.get("recommended_discharge_hours") or []
        risk_items = risk.get("items") or []
        discharge_lines = [
            f"{idx}. {item.get('time')}，预测价 {_safe_money(item.get('predicted_price'))}，风险 {item.get('risk_level')}"
            for idx, item in enumerate(discharge[:5], 1)
        ]
        risk_lines = [
            f"{idx}. {item.get('hour')}，风险 {item.get('risk_level')}，预测价 {_safe_money(item.get('predicted_price'))}"
            for idx, item in enumerate(risk_items[:5], 1)
        ]
        weather_text = f"{weather.get('city') or '-'} 气温约 {weather.get('min_temperature')} 至 {weather.get('max_temperature')} 摄氏度" if weather else "暂无天气摘要"
        model_rows = model.get("error_rows") or []
        model_text = "真实值回填样本不足，暂不能严谨判断模型误差" if not model_rows else f"MAE 约 {model_rows[0].get('mae')}，RMSE 约 {model_rows[0].get('rmse')}"
        return (
            "结论：当前交易风险应重点关注高价放电窗口、风险复核时段、天气负荷扰动和模型误差状态，不能只按单个最高价点决策。\n\n"
            "高价/放电候选时段：\n" + ("\n".join(discharge_lines) if discharge_lines else "暂无明确高价放电候选时段。")
            + "\n\n风险复核时段：\n" + ("\n".join(risk_lines) if risk_lines else "暂无明确高风险时段。")
            + f"\n\n数据依据：未来24小时均价约 {_safe_money(storage.get('avg_price'))}，峰谷价差约 {_safe_money(storage.get('spread'))}；天气参考：{weather_text}；模型误差参考：{model_text}。"
            + "\n\n业务建议：晚高峰和高价窗口优先做敞口复核，低价窗口可作为采购或储能充电参考，最终仍需结合实时市场、合同约束、SOC 和人工复核执行。"
        )
    if intent == "model_error_status" and _storage_boundary_note(decision.normalized_question):
        rows = first.get("error_rows") or []
        if rows:
            row = rows[0]
            base = (
                f"结论：当前有模型误差记录，样本数 {row.get('sample_count')}，MAE 约 {row.get('mae')}，RMSE 约 {row.get('rmse')}。"
                "\n\n依据：prediction_tracking 真实值回填记录。"
            )
        else:
            base = "结论：当前真实值回填样本不足，暂不能严谨判断模型最近是否变差。"
        return base + _storage_boundary_note(decision.normalized_question)
    if intent == "model_error_status":
        rows = first.get("error_rows") or []
        if rows:
            row = rows[0]
            return f"结论：最新模型误差样本为 {row.get('model_version')}，样本数 {row.get('sample_count')}，MAE 约 {row.get('mae')}，RMSE 约 {row.get('rmse')}。\n\n数据依据：prediction_tracking 真实值回填记录。"
        return "结论：当前真实值回填样本不足，暂不能严谨判断模型误差状态。"
    if intent == "report_summary":
        summary = first.get("summary") or {}
        core = summary.get("executive_summary") or summary.get("management_summary") or summary.get("market_overview") or "当前报告摘要字段不足。"
        return f"结论：最新报告 {first.get('report_id') or '-'} 当前{'可用' if first.get('available') else '未生成'}。\n\n{core}"
    if intent == "tariff_query":
        if not first.get("available"):
            return f"结论：未匹配到对应光伏电价规则。\n\n数据依据：{first.get('message') or '电价规则表暂无可用记录。'}\n\n业务建议：请补充省、市和具体并网日期后复核。\n\n风险提示：缺少精确并网日期时，按年份匹配可能存在口径偏差。"
        total = first.get("total_price")
        total_text = f"{total} 元/kWh" if total is not None else "需按上网电价与补贴另行核算"
        return (
            f"结论：{first.get('province') or ''}{first.get('city') or ''} 在 {first.get('grid_date') or '指定并网日期'} 匹配到的光伏总价为 {total_text}。\n\n"
            f"数据依据：适用期间 {first.get('start_date') or '-'} 至 {first.get('end_date') or '-'}；上网电价 {first.get('on_grid_price')} 元/kWh；补贴电价 {first.get('subsidy_price')} 元/kWh；补贴年限 {first.get('subsidy_years') or '-'} 年。\n\n"
            f"原因解释：系统优先按省市和并网日期匹配《上线用—初始化电价表》入库规则，命中后返回上网电价、补贴和总价字段。\n\n"
            f"业务建议：入账前建议再核对政策文件号、电站并网证明和供电局结算单。\n\n"
            f"风险提示：{first.get('remark') or '若并网日期、项目类型或地方补贴口径不同，最终结算价可能变化。'}"
        )
    if intent == "station_tariff_check":
        if not first.get("available"):
            return f"结论：未找到该电站的电价核对记录。\n\n数据依据：{first.get('message') or '-'}\n\n业务建议：请补充电站编码或导入最新电费清单。\n\n风险提示：未完成核对前不建议自动覆盖系统电价。"
        return (
            f"结论：电站 {first.get('station_id') or '-'} 已找到核对记录，系统电价 {first.get('system_price')} 元/kWh，供电局电价 {first.get('grid_price')} 元/kWh。\n\n"
            f"数据依据：地区 {first.get('province') or ''}{first.get('city') or ''}{first.get('district') or ''}；并网日期 {first.get('grid_date') or '-'}；国补 {first.get('national_subsidy')}，省补 {first.get('provincial_subsidy')}。\n\n"
            f"原因解释：系统从《浙江电费清单》等核对数据中按电站编码匹配结算口径。\n\n"
            f"业务建议：差异标记为 {first.get('difference_flag') or '未记录'}，应由业务人员复核供电局账单和系统价格。\n\n"
            f"风险提示：{first.get('remark') or '如未与供电局达成一致，不应直接按单方数据调整结算。'}"
        )
    if intent == "tariff_policy_search":
        items = first.get("items") or []
        rows = [f"{idx}. {item.get('doc_number') or '-'} {item.get('title') or '-'}：{str(item.get('summary') or '')[:120]}" for idx, item in enumerate(items[:5], 1)]
        return (
            "结论：已按问题检索光伏电价政策与文件摘要。\n\n"
            "数据依据：\n" + ("\n".join(rows) if rows else "未检索到明确政策文档。")
            + "\n\n原因解释：系统优先搜索已入库政策摘要和知识库 Markdown 文件。\n\n业务建议：将命中的文号、执行时间、补贴口径与电站并网日期一起核对。\n\n风险提示：政策摘要不能替代原文，正式结算需回看政策文件原件。"
        )
    if intent == "market_power_price_query":
        if not first.get("available"):
            return f"结论：未匹配到市电价格规则。\n\n数据依据：{first.get('message') or '-'}\n\n业务建议：请补充业务月份和省份。\n\n风险提示：综合电价口径需确认是否包含辅助分摊费用。"
        return (
            f"结论：{first.get('province') or '-'} {first.get('business_month') or '-'} 的综合电价为 {first.get('total_price')} 元/kWh。\n\n"
            f"数据依据：市场电价/煤电参考价 {first.get('power_price')}；辅助分摊费用 {first.get('auxiliary_cost')}；备注 {first.get('remark') or '-'}。\n\n"
            "原因解释：系统按业务月份和省份匹配市电汇总规则。\n\n业务建议：用于报价或成本测算前，应确认业务月份、结算周期和分摊项是否一致。\n\n风险提示：市场电价规则可能随月份更新，需使用最新入库版本。"
        )
    if intent == "southern_grid_tax_query":
        if not first.get("available"):
            return f"结论：未匹配到南网税率规则。\n\n数据依据：{first.get('message') or '-'}\n\n业务建议：请补充省、市、区县或电站编码。\n\n风险提示：代扣代缴口径需由财务或税务人员最终确认。"
        return (
            f"结论：{first.get('province') or ''}{first.get('city') or ''}{first.get('district') or ''} 的暂准扣税/代扣口径税率为 {first.get('deduction_rate')}。\n\n"
            f"数据依据：回款金额公式为 {first.get('payment_formula') or '-'}；规则说明：{first.get('tax_remark') or '-'}。\n\n"
            "原因解释：系统从南网税率问题表中按地区匹配代扣代缴、完税和回款公式字段。\n\n业务建议：应结合电费结算单、发票和完税凭证进行复核。\n\n风险提示：税率字段标注为暂准时，不应直接作为最终财务入账依据。"
        )
    if intent == "knowledge_search":
        items = first.get("items") or []
        rows = [f"{idx}. {item.get('title') or '-'}：{str(item.get('snippet') or '')[:900]}" for idx, item in enumerate(items[:3], 1)]
        return (
            "结论：已完成知识库检索。\n\n"
            "数据依据：\n" + ("\n".join(rows) if rows else "未检索到高相关文档。")
            + "\n\n原因解释：系统通过当前混合检索链路返回可追溯知识片段。\n\n业务建议：将检索结果作为 AI 回答依据，并在正式引用前打开原文复核。\n\n风险提示：回答必须受 citation 和 source_type 约束；证据不足时返回 unavailable。"
        )
    if intent == "general_query":
        if _storage_boundary_note(decision.normalized_question):
            return (
                "结论：没有储能 SOC、可用容量、额定功率和效率等设备参数时，不能给具体充放电量。\n\n"
                "原因：具体充放电量取决于电池当前 SOC、可用容量、功率上限、效率损耗、循环寿命、合同约束和并网约束。\n\n"
                "建议：可以先做方向性判断，例如低价时段关注充电机会、高价时段关注放电价值；但执行前必须补齐设备参数和交易规则。"
            ) + _storage_boundary_note(decision.normalized_question)
        q = _compact_match_text(decision.normalized_question)
        if "你是谁" in q:
            return "我是电价预测专家助手，可以帮你分析电价预测、负荷天气、尖峰风险、交易策略和模型误差。"
        if any(term in q for term in ["你好", "早上好", "下午好", "晚上好"]):
            return "你好，我可以帮助你做电价预测分析、风险解释和交易策略复核。"
        if any(term in q for term in ["谢谢", "感谢"]):
            return "不客气，有需要可以继续问我电价、负荷、天气或交易策略问题。"
        if any(term in q for term in ["一句话", "简短"]):
            return "可以，我会尽量用一句话简短回答。"
        if "中文" in q:
            return "可以，我会使用中文回答。"
        return "结论：这是通用问题。如果你需要我分析电价、负荷、天气数据范围、储能策略、模型误差或报告内容，可以直接继续提问。"
    return "结论：当前系统已查询相关数据，但该问题需要进一步明确业务口径。请补充具体时段、数据域或交易场景。"


def _state_from_answer(session_id: str, decision: IntentDecision, answer: str, results: list[ToolResult], run_id: str) -> ConversationState:
    topic = ""
    focus_time = ""
    focus_metric = ""
    focus_value = ""
    first = _first(results)
    if decision.intent == "forecast_min_price":
        topic, focus_time, focus_metric, focus_value = "low_price_window", str(first.get("min_time") or ""), "predicted_price", str(first.get("min_price") or "")
    elif decision.intent == "forecast_max_price":
        topic, focus_time, focus_metric, focus_value = "high_price_window", str(first.get("max_time") or ""), "predicted_price", str(first.get("max_price") or "")
    elif decision.intent in {"forecast_risk_hours", "risk_reason"}:
        items = first.get("items") or []
        topic = "high_risk_hour"
        focus_time = str(items[0].get("hour") if items else first.get("time") or "")
        focus_metric = "risk_level"
        focus_value = str(items[0].get("risk_level") if items else first.get("risk_level") or "")
    elif decision.intent == "storage_discharge_advice":
        hours = first.get("recommended_discharge_hours") or []
        topic = "storage_discharge"
        focus_time = str(hours[0].get("time") if hours else "")
        focus_metric = "predicted_price"
        focus_value = str(hours[0].get("predicted_price") if hours else "")
    elif decision.intent in {"low_price_reason", "high_price_reason"}:
        topic = "low_price_window" if decision.intent == "low_price_reason" else "high_price_window"
        focus_time = str(first.get("time") or "")
        focus_metric = "predicted_price"
        focus_value = str(first.get("predicted_price") or "")
    return ConversationState(
        session_id=session_id,
        last_intent=decision.intent,
        last_topic=topic,
        last_focus_time=focus_time,
        last_focus_metric=focus_metric,
        last_focus_value=focus_value,
        last_run_id=run_id,
        last_answer_summary=answer[:300],
    )


def answer_chat_accurate(
    question: str,
    session_id: str | None = None,
    run_id: str = "latest",
    market: str | None = None,
    date: str | None = None,
    page_context: dict[str, Any] | None = None,
    scenario: str = "power_trading",
    user_role: str = "trader",
    answer_style: str = "analysis",
    model_provider: str = "auto",
    debug: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    total_started = time.perf_counter()
    timings_ms: dict[str, float] = {}
    stage_started = time.perf_counter()
    clean_question = normalize_question(question)
    timings_ms["input_normalizer_ms"] = _timing_ms(stage_started)
    session_id = session_id or "chat_" + uuid.uuid4().hex[:12]
    security_reason = _security_refusal_reason(clean_question)
    if security_reason:
        return _security_refusal_payload(
            session_id=session_id,
            model_provider=model_provider,
            debug=debug,
            reason=security_reason,
        )
    unavailable_reason = _explicit_unavailable_reason(clean_question)
    if unavailable_reason:
        return _unavailable_payload(
            session_id=session_id,
            model_provider=model_provider,
            debug=debug,
            reason=unavailable_reason,
        )
    trace = TraceManager(clean_question)
    trace.step("input_normalizer", normalized_question=clean_question)
    stage_started = time.perf_counter()
    previous = get_conversation_state(session_id)
    resolved_decision = resolve_followup(clean_question, previous)
    timings_ms["context_resolver_ms"] = _timing_ms(stage_started)
    trace.step(
        "context_resolver",
        resolved=bool(resolved_decision),
        last_intent=previous.last_intent if previous else "",
        last_topic=previous.last_topic if previous else "",
    )
    stage_started = time.perf_counter()
    decision = resolved_decision or route_intent(clean_question)
    timings_ms["intent_router_ms"] = _timing_ms(stage_started)
    if market and "market" not in decision.entities:
        decision.entities["market"] = market
    if date and "date" not in decision.entities:
        decision.entities["date"] = date

    trace.set(normalized_question=decision.normalized_question or clean_question, resolved_context=previous.__dict__ if previous else {})
    trace.step("intent_router", intent=decision.intent, confidence=decision.confidence, entities=decision.entities)
    fast_payload = _daily_fast_path_payload(
        question=clean_question,
        decision=decision,
        session_id=session_id,
        answer_style=answer_style,
        model_provider=model_provider,
        debug=debug,
        trace=trace,
        timings_ms=timings_ms,
        total_started=total_started,
    )
    if fast_payload is not None:
        return fast_payload
    stage_started = time.perf_counter()
    tool_results = _execute_tools(decision, run_id, clean_question)
    timings_ms["tool_executor_ms"] = _timing_ms(stage_started)
    trace.step(
        "tool_executor",
        tools_called=[{"tool": item.name, "input": item.input, "success": item.success, "error_message": item.error_message} for item in tool_results],
    )
    plan = plan_answer(decision.intent)
    trace.step("answer_planner", answer_mode=plan.answer_mode, llm_used=plan.use_llm)
    answer = _build_answer(decision, tool_results)
    draft_answer = answer
    evidence = _evidence(tool_results)
    expert_plan = plan_expert_answer(decision.intent, answer_style=answer_style, model_provider=model_provider)
    rag_result: dict[str, Any] = {"available": False, "items": [], "retrieval": {"enabled": False}}
    stage_started = time.perf_counter()
    use_rag, rag_trigger_info = _rag_trigger_decision(decision.intent, expert_plan.task_type, clean_question)
    timings_ms["rag_trigger_ms"] = _timing_ms(stage_started)
    if use_rag:
        try:
            stage_started = time.perf_counter()
            rag_result = rag_search(
                clean_question,
                top_k=_rag_top_k(),
                domain=_rag_domain_hint(clean_question) if decision.intent == "knowledge_search" else "",
            )
            timings_ms["rag_total_ms"] = _timing_ms(stage_started)
            evidence.extend(_rag_evidence(rag_result))
            trace.step(
                "rag_retriever",
                enabled=True,
                trigger=rag_trigger_info,
                available=bool(rag_result.get("available")),
                hits=len(rag_result.get("items") or []),
                retrieval=rag_result.get("retrieval") or {},
            )
        except Exception as exc:
            timings_ms["rag_total_ms"] = _timing_ms(stage_started)
            rag_result = {"available": False, "items": [], "retrieval": {"enabled": True, "error": sanitize_error(exc)}}
            trace.step("rag_retriever", enabled=True, trigger=rag_trigger_info, success=False, error=sanitize_error(exc))
    else:
        timings_ms["rag_total_ms"] = 0.0
        trace.step("rag_retriever", enabled=False, **rag_trigger_info)
    rag_required_unavailable = bool(
        use_rag
        and not rag_result.get("citations")
        and decision.intent in {"knowledge_search", "general_query"}
        and not _storage_boundary_note(clean_question)
    )
    if rag_required_unavailable:
        answer = "当前知识库没有达到相关度门槛且可核验的证据，无法据此回答该问题。"
        draft_answer = answer
    stage_started = time.perf_counter()
    context_pack = build_context_pack(
        question=clean_question,
        decision=decision,
        results=tool_results,
        evidence=evidence,
        run_id=run_id,
        rag_result=rag_result,
    )
    timings_ms["context_pack_ms"] = _timing_ms(stage_started)
    llm_used = False
    model_used = False
    model_error = ""
    model_status: dict[str, Any] = {}
    llm_task_type = expert_plan.task_type
    if use_rag and llm_task_type == "daily_chat":
        llm_task_type = "business_answer"
    skip_daily_llm = _should_skip_llm_for_daily_chat(decision.intent, llm_task_type, clean_question)
    if rag_required_unavailable or not _should_use_llm(decision.intent) or skip_daily_llm:
        model_status = {"provider": "deterministic", "model": "tool_answer", "fallback": False}
        trace.step(
            "llm_router",
            success=True,
            provider="deterministic",
            reason=(
                "rag_evidence_unavailable"
                if rag_required_unavailable
                else "daily_chat_fast_path"
                if skip_daily_llm
                else "deterministic_intent"
            ),
        )
        timings_ms["llm_generate_ms"] = 0.0
    elif _llm_enabled():
        try:
            stage_started = time.perf_counter()
            messages = build_expert_messages(
                question=clean_question,
                context_pack=context_pack,
                answer_style=normalize_answer_style(answer_style),
                draft_answer=draft_answer,
                task_type=llm_task_type,
            )
            timings_ms["prompt_build_ms"] = _timing_ms(stage_started)
            stage_started = time.perf_counter()
            llm_answer, model_status = LLMRouter().generate_answer(
                messages,
                task_type=llm_task_type,
                requested_provider=expert_plan.preferred_provider,
                temperature=expert_plan.temperature,
                max_tokens=expert_plan.max_tokens,
            )
            timings_ms["llm_generate_ms"] = _timing_ms(stage_started)
            model_used = True
            if llm_answer and not _looks_like_reasoning_leak(llm_answer):
                styled_llm_answer = apply_answer_style_contract(llm_answer, answer_style, decision.intent, clean_question)
                answer = _preserve_required_business_terms(decision.intent, styled_llm_answer, draft_answer)
                llm_used = True
            elif llm_answer:
                trace.step("llm_router", success=True, used_for_answer=False, reason="reasoning_leak", **model_status)
        except Exception as exc:
            model_error = f"模型调用失败，已使用工具事实模板兜底：{sanitize_error(exc)}"
            trace.step("llm_router", success=False, error=model_error, requested_provider=model_provider)
    else:
        model_status = {"provider": "template", "model": "tool_fallback", "fallback": True}
        trace.step("llm_router", success=True, provider="template", reason="disabled_by_env")
        timings_ms["llm_generate_ms"] = 0.0
    if model_status:
        trace.step("llm_router", success=not bool(model_error), **model_status)
    timings_ms.setdefault("llm_generate_ms", 0.0)
    stage_started = time.perf_counter()
    answer, guard_result = guard_answer(decision.intent, answer, evidence)
    answer = sanitize_answer_for_display(answer)
    timings_ms["answer_guard_ms"] = _timing_ms(stage_started)
    trace.step("answer_guard", guard_result=guard_result)
    timings_ms["total_ms"] = _timing_ms(total_started)
    trace_payload = trace.finish(intent=decision.intent, intent_confidence=decision.confidence, llm_used=llm_used, answer_mode=plan.answer_mode, guard_result=guard_result)
    tool_calls = [
        {"tool_name": item.name, "input": item.input, "success": item.success, "output": item.output, "error_message": item.error_message}
        for item in tool_results
    ]
    if persist:
        save_ai_trace_record(
            session_id=session_id,
            question=clean_question,
            intent=decision.intent,
            answer=answer,
            tools=tool_calls,
            evidence=evidence,
            guard_result={"result": guard_result},
            trace_payload=trace_payload,
        )
        save_conversation_state(_state_from_answer(session_id, decision, answer, tool_results, run_id))
        save_chat_exchange(
            session_id=session_id,
            question=clean_question,
            answer=answer,
            intent=decision.intent,
            evidence=evidence,
            tool_calls=tool_calls,
            user_role=user_role,
            scenario=scenario,
            trace_id=trace.trace_id,
        )
    focus_periods = [
        item.get("time") or item.get("hour")
        for item in (
            _first(tool_results).get("recommended_discharge_hours")
            or _first(tool_results).get("recommended_charge_hours")
            or _first(tool_results).get("items")
            or []
        )
        if item.get("time") or item.get("hour")
    ][:6]
    data_used = _data_used(tool_results)
    if rag_result.get("items"):
        data_used["knowledge"] = True
    rag_citations = list(rag_result.get("citations") or [])
    top_rag_score = max(
        [float(item.get("score") or 0.0) for item in rag_citations],
        default=0.0,
    )
    rag_confidence = (
        "high"
        if top_rag_score >= 0.65
        else "medium"
        if top_rag_score >= 0.4
        else "low"
        if rag_citations
        else "none"
    )
    actual_run_id = run_id if run_id and run_id != "latest" else None
    tool_source_types: list[str] = []
    response_domain = str(rag_result.get("domain") or "")
    model_version = ""
    feature_version = ""
    for result in tool_results:
        output = result.output or {}
        meta = output.get("meta") if isinstance(output.get("meta"), dict) else {}
        if not actual_run_id:
            actual_run_id = str(output.get("run_id") or meta.get("run_id") or "") or None
        source_value = str(output.get("source_type") or meta.get("source_type") or "")
        if source_value:
            tool_source_types.append(source_value)
        if not response_domain:
            response_domain = str(output.get("domain") or meta.get("domain") or "")
        model_version = model_version or str(output.get("model_version") or meta.get("model_version") or "")
        feature_version = feature_version or str(output.get("feature_version") or meta.get("feature_version") or "")
    response_source_type = str(
        rag_result.get("source_type") or (tool_source_types[0] if tool_source_types else "unavailable")
    )
    if rag_citations and any(item.get("tool") != "rag_hybrid_search" for item in evidence):
        response_source_type = "derived"
    public_payload: dict[str, Any] = {
        "session_id": session_id,
        "answer": answer,
        "source_type": response_source_type,
        "domain": response_domain,
        "run_id": actual_run_id,
        "model_version": model_version or None,
        "feature_version": feature_version or None,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "confidence": rag_confidence,
        "citations": rag_citations,
        "evidence": evidence,
        "answer_style": normalize_answer_style(answer_style),
        "model_provider_used": model_status.get("provider") or "",
        "model_provider_requested": model_provider,
        "model_fallback": bool(model_status.get("fallback")),
        "llm_used": llm_used,
        "data_used": data_used,
        "evidence_summary": _evidence_summary(evidence),
        "knowledge_evidence_summary": [
            f"{item.get('title') or item.get('source') or '知识库'}"
            for item in (rag_result.get("items") or [])[:3]
        ],
        "warnings": [model_error] if model_error else [],
        "risk_level": str(_first(tool_results).get("risk_level") or ""),
        "focus_periods": focus_periods,
        "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
    if debug:
        public_payload.update(
            {
                "intent": decision.intent,
                "confidence": decision.confidence,
                "entities": decision.entities,
                "answer_mode": plan.answer_mode,
                "task_type": llm_task_type,
                "model_used": model_used,
                "model_error": model_error,
                "local_model": model_status,
                "tools": [{"name": item.name, "input": item.input, "success": item.success} for item in tool_results],
                "tool_calls": tool_calls,
                "evidence": evidence,
                "rag": rag_result,
                "rag_trigger": rag_trigger_info,
                "timings_ms": timings_ms,
                "trace": trace_payload,
                "agent_trace": trace_payload.get("steps", []),
                "trace_id": trace.trace_id,
                "related_actions": [],
                "suggestions": [],
                "complexity": "simple" if plan.answer_mode == "deterministic_template" else "complex",
                "workflow": ["input_normalizer", "context_resolver", "intent_router", "tool_executor", "answer_planner", "answer_guard"],
            }
        )
    return jsonable(public_payload)
