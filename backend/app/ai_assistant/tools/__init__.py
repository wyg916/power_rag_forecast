from __future__ import annotations

from typing import Any

from ...source_contract import normalize_tool_result
from ...ai.tool_registry import get_high_risk_hours, get_model_error_summary
from ...services.controlled_business_query_service import get_data_freshness, query_business_data
from .forecast_tools import explain_high_price_hour, explain_low_price_hour, get_forecast_metrics
from .knowledge_tools import search_business_knowledge
from .report_tools import get_report_summary
from .storage_tools import get_storage_charge_windows, get_storage_discharge_windows
from .tariff_tools import (
    check_station_tariff,
    query_market_power_price,
    query_pv_tariff,
    query_southern_grid_tax_rule,
    search_tariff_policy,
)
from .text_tools import explain_user_provided_text
from .time_tools import get_current_date_context
from .weather_tools import get_load_summary, get_weather_summary


TOOLS = {
    "get_current_date_context": get_current_date_context,
    "get_data_freshness": get_data_freshness,
    "query_business_data": query_business_data,
    "get_forecast_metrics": get_forecast_metrics,
    "get_high_risk_hours": get_high_risk_hours,
    "explain_low_price_hour": explain_low_price_hour,
    "explain_high_price_hour": explain_high_price_hour,
    "get_storage_discharge_windows": get_storage_discharge_windows,
    "get_storage_charge_windows": get_storage_charge_windows,
    "get_weather_summary": get_weather_summary,
    "get_load_summary": get_load_summary,
    "get_report_summary": get_report_summary,
    "get_model_error_summary": get_model_error_summary,
    "explain_user_provided_text": explain_user_provided_text,
    "query_pv_tariff": query_pv_tariff,
    "check_station_tariff": check_station_tariff,
    "search_tariff_policy": search_tariff_policy,
    "query_market_power_price": query_market_power_price,
    "query_southern_grid_tax_rule": query_southern_grid_tax_rule,
    "search_business_knowledge": search_business_knowledge,
}


def execute_tool(name: str, **kwargs: Any) -> dict[str, Any]:
    output = TOOLS[name](**kwargs)
    return normalize_tool_result(name, output, requested_run_id=kwargs.get("run_id"))
