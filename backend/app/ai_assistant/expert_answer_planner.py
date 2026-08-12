from __future__ import annotations

from dataclasses import dataclass


COMPLEX_INTENTS = {
    "trading_risk_summary",
    "forecast_overview",
    "forecast_risk_hours",
    "risk_reason",
    "high_price_reason",
    "low_price_reason",
    "weather_impact_on_price",
    "model_error_status",
    "model_retrain_suggestion",
    "report_summary",
    "knowledge_search",
}

DETERMINISTIC_INTENTS = {
    "current_date_query",
    "prediction_window_query",
    "weather_data_latest_time",
    "price_data_latest_time",
    "load_data_latest_time",
    "database_table_freshness",
    "data_sql_query",
    "forecast_max_price",
    "forecast_min_price",
    "forecast_avg_price",
    "forecast_spread",
}


@dataclass(frozen=True)
class ExpertAnswerPlan:
    task_type: str
    preferred_provider: str
    temperature: float
    max_tokens: int


def normalize_answer_style(answer_style: str | None) -> str:
    value = (answer_style or "professional_brief").strip()
    aliases = {
        "analysis": "professional_brief",
        "brief": "professional_brief",
        "deep": "professional_deep",
        "business": "business_advice",
        "plain": "plain_language",
    }
    return aliases.get(value, value)


def plan_expert_answer(intent: str, answer_style: str | None = None, model_provider: str = "auto") -> ExpertAnswerPlan:
    style = normalize_answer_style(answer_style)
    forced = (model_provider or "auto").strip().lower()
    if intent == "general_query" or style == "daily_chat":
        task_type = "daily_chat"
    elif intent in COMPLEX_INTENTS or style in {"professional_deep", "business_advice", "report_style"}:
        task_type = "complex_analysis"
    elif intent in DETERMINISTIC_INTENTS:
        task_type = "simple_data_answer"
    else:
        task_type = "business_answer"

    preferred = forced if forced in {"deepseek", "kimi", "mimo", "ollama"} else "auto"
    max_tokens_by_style = {
        "daily_chat": 500,
        "plain_language": 600,
        "professional_brief": 700,
        "business_advice": 900,
        "report_style": 1100,
        "professional_deep": 1200,
    }
    # Reasoning-capable providers can spend most of a short budget on private
    # reasoning before emitting the user-visible answer. Reserve enough room
    # for both phases on full business-context prompts.
    max_tokens = (
        4096
        if task_type == "complex_analysis"
        else max_tokens_by_style.get(style, 900)
    )
    temperature = 0.25 if task_type != "daily_chat" else 0.45
    return ExpertAnswerPlan(task_type=task_type, preferred_provider=preferred, temperature=temperature, max_tokens=max_tokens)
