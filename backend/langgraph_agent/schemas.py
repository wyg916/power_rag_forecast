from __future__ import annotations


TOOL_DATA_SOURCE: dict[str, str] = {
    "get_prediction_overview": "prediction",
    "get_forecast_extremes": "prediction",
    "get_high_risk_hours": "prediction",
    "get_hour_detail": "prediction",
    "build_hour_risk_evidence": "prediction",
    "get_trading_advice": "prediction",
    "get_storage_advice": "prediction",
    "get_weather_forecast": "weather",
    "get_load_forecast": "load",
    "get_renewable_forecast": "renewable",
    "get_market_history": "history",
    "compare_with_yesterday": "history",
    "get_model_explain": "model",
    "get_model_error_summary": "model",
    "get_risk_level": "risk",
    "search_knowledge": "knowledge",
    "get_report_summary": "report",
    "get_data_status": "data_status",
}


PROFESSIONAL_INTENTS = {
    "forecast_overview",
    "forecast_extreme",
    "risk_hours",
    "hour_explain",
    "factor_analysis",
    "load_analysis",
    "renewable_analysis",
    "strategy_advice",
    "storage_advice",
    "compare_history",
    "model_status",
    "report_summary",
    "data_status",
}


INTENT_TOOL_PLAN: dict[str, list[str]] = {
    "forecast_overview": ["get_prediction_overview", "get_forecast_extremes", "get_risk_level"],
    "forecast_extreme": ["get_forecast_extremes"],
    "risk_hours": ["get_high_risk_hours", "get_risk_level"],
    "hour_explain": ["get_hour_detail", "build_hour_risk_evidence"],
    "factor_analysis": [
        "get_prediction_overview",
        "get_forecast_extremes",
        "get_load_forecast",
        "get_weather_forecast",
        "get_renewable_forecast",
        "get_market_history",
        "get_model_explain",
        "get_risk_level",
        "get_high_risk_hours",
        "get_trading_advice",
        "search_knowledge",
    ],
    "weather_analysis": ["get_weather_forecast", "search_knowledge"],
    "load_analysis": ["get_load_forecast", "search_knowledge"],
    "renewable_analysis": ["get_renewable_forecast", "search_knowledge"],
    "strategy_advice": ["get_trading_advice", "get_high_risk_hours", "get_risk_level"],
    "storage_advice": ["get_storage_advice", "get_forecast_extremes"],
    "compare_history": ["compare_with_yesterday", "get_market_history"],
    "model_status": ["get_model_error_summary", "get_model_explain"],
    "report_summary": ["get_report_summary", "get_prediction_overview", "get_high_risk_hours"],
    "data_status": ["get_data_status"],
    "general_analysis": ["get_forecast_extremes", "get_high_risk_hours", "get_trading_advice"],
}
