from __future__ import annotations

import os

from ..schemas import AnswerPlan


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
    "model_error_status",
}


def plan_answer(intent: str) -> AnswerPlan:
    if intent in DETERMINISTIC_INTENTS:
        return AnswerPlan("deterministic_template", False, intent)
    if os.environ.get("LOCAL_LLM_SUMMARY_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}:
        if intent == "general_query":
            return AnswerPlan("llm_general", True, intent)
        return AnswerPlan("tool_llm_summary", True, intent)
    if intent == "general_query":
        return AnswerPlan("tool_template", False, intent)
    return AnswerPlan("tool_template", False, intent)
