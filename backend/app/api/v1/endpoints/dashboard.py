from __future__ import annotations

from fastapi import APIRouter

from ....services.dashboard_home_service import (
    dashboard_ai_suggestions_payload,
    dashboard_context_payload,
    dashboard_data_health_payload,
    dashboard_forecast_metrics_payload,
    dashboard_kpi_payload,
    dashboard_model_status_payload,
    dashboard_overview_payload,
    dashboard_strategy_execution_payload,
    dashboard_supply_demand_risk_payload,
    dashboard_task_reminders_payload,
)
from ....source_contract import SourceType, attach_source_meta, resolve_forecast_source


router = APIRouter()


def _with_dashboard_meta(payload: dict) -> dict:
    _, _, meta = resolve_forecast_source("latest")
    if meta.get("source_type") in {"real", "historical"}:
        meta = {
            **meta,
            "source_type": SourceType.DERIVED.value,
            "evidence": list(meta.get("evidence") or []) + [{"derivation": "dashboard_read_model"}],
        }
    return attach_source_meta(payload, meta)


@router.get("/api/dashboard/overview")
def dashboard_overview() -> dict:
    return _with_dashboard_meta(dashboard_overview_payload())


@router.get("/api/dashboard/context")
def dashboard_context() -> dict:
    return _with_dashboard_meta(dashboard_context_payload())


@router.get("/api/dashboard/kpis")
def dashboard_kpis() -> dict:
    return _with_dashboard_meta(dashboard_kpi_payload())


@router.get("/api/dashboard/supply-demand-risk-24h")
def dashboard_supply_demand_risk_24h() -> dict:
    return _with_dashboard_meta(dashboard_supply_demand_risk_payload())


@router.get("/api/dashboard/forecast-metrics")
def dashboard_forecast_metrics() -> dict:
    return _with_dashboard_meta(dashboard_forecast_metrics_payload())


@router.get("/api/dashboard/ai-suggestions")
def dashboard_ai_suggestions() -> dict:
    return _with_dashboard_meta(dashboard_ai_suggestions_payload())


@router.get("/api/dashboard/strategy-execution-summary")
def dashboard_strategy_execution_summary() -> dict:
    return _with_dashboard_meta(dashboard_strategy_execution_payload())


@router.get("/api/dashboard/model-status")
def dashboard_model_status() -> dict:
    return _with_dashboard_meta(dashboard_model_status_payload())


@router.get("/api/dashboard/data-health")
def dashboard_data_health() -> dict:
    return _with_dashboard_meta(dashboard_data_health_payload())


@router.get("/api/dashboard/task-reminders")
def dashboard_task_reminders(limit: int = 8) -> dict:
    normalized_limit = max(1, min(limit, 50))
    return _with_dashboard_meta(dashboard_task_reminders_payload(limit=normalized_limit))
