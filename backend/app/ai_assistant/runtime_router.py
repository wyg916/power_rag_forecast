from __future__ import annotations

from enum import StrEnum

from .core.intent_router import route_intent


class AssistantRoute(StrEnum):
    GENERAL_CHAT = "GENERAL_CHAT"
    CHATBI = "CHATBI"
    RAG_QA = "RAG_QA"
    BUSINESS_ANALYSIS = "BUSINESS_ANALYSIS"
    BUSINESS_ADVICE = "BUSINESS_ADVICE"
    REPORT_GENERATION = "REPORT_GENERATION"
    FILE_QA = "FILE_QA"
    VISION_ANALYSIS = "VISION_ANALYSIS"
    PREMIUM_DEEP_ANALYSIS = "PREMIUM_DEEP_ANALYSIS"


GENERAL_INTENTS = {
    "brief_answer_request", "capability", "current_date_query", "greeting",
    "identity", "multi_daily_chat", "plain_language_intro", "thanks", "time", "weekday",
}
CHATBI_INTENTS = {
    "data_sql_query", "database_table_freshness", "load_data_latest_time",
    "price_data_latest_time", "weather_data_latest_time",
}
RAG_INTENTS = {"knowledge_search", "tariff_policy_search"}
ADVICE_INTENTS = {
    "storage_charge_advice", "storage_discharge_advice", "storage_spread_analysis",
    "trading_risk_summary",
}
REPORT_INTENTS = {"report_summary"}


def route_assistant_request(
    question: str,
    *,
    answer_style: str = "professional_brief",
    mode: str = "",
    requested_tier: str = "standard",
    has_image: bool = False,
) -> AssistantRoute:
    """Select the product route before opening AnalysisPlan or RAG runtime."""

    if (requested_tier or "standard").strip().lower() == "premium":
        return AssistantRoute.PREMIUM_DEEP_ANALYSIS
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == "vision" or has_image:
        return AssistantRoute.VISION_ANALYSIS
    if normalized_mode == "file":
        return AssistantRoute.FILE_QA
    if normalized_mode == "chatbi":
        return AssistantRoute.CHATBI
    if normalized_mode == "rag":
        return AssistantRoute.RAG_QA
    style = (answer_style or "professional_brief").strip().lower()
    if style == "chatbi":
        return AssistantRoute.CHATBI
    intent = route_intent(question).intent
    if intent in GENERAL_INTENTS:
        return AssistantRoute.GENERAL_CHAT
    if intent in CHATBI_INTENTS:
        return AssistantRoute.CHATBI
    if intent in RAG_INTENTS:
        return AssistantRoute.RAG_QA
    if style == "report_style" or intent in REPORT_INTENTS:
        return AssistantRoute.REPORT_GENERATION
    if style == "business_advice" or intent in ADVICE_INTENTS:
        return AssistantRoute.BUSINESS_ADVICE
    return AssistantRoute.BUSINESS_ANALYSIS


def route_requires_rag(route: AssistantRoute) -> bool:
    return route == AssistantRoute.RAG_QA


def answer_strategy(route: AssistantRoute) -> str:
    return {
        AssistantRoute.GENERAL_CHAT: "direct_answer",
        AssistantRoute.CHATBI: "data_analysis",
        AssistantRoute.RAG_QA: "rag_answer",
        AssistantRoute.FILE_QA: "file_qa",
        AssistantRoute.VISION_ANALYSIS: "vision_analysis",
        AssistantRoute.BUSINESS_ADVICE: "action_advice",
        AssistantRoute.PREMIUM_DEEP_ANALYSIS: "premium_deep_analysis",
        AssistantRoute.REPORT_GENERATION: "premium_deep_analysis",
        AssistantRoute.BUSINESS_ANALYSIS: "data_analysis",
    }[route]
