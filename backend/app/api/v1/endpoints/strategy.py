from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ....core.security import CurrentUser, require_permission
from ....platform_services import generate_anomaly_explanations, generate_strategy_advice
from ....repositories.audit_repository import write_audit_log
from ....services.ui_platform_service import _read_runtime_settings, response, save_system_config


router = APIRouter()


@router.post("/api/strategy/generate")
def strategy_generate(_: Annotated[CurrentUser, Depends(require_permission("task:run"))]) -> dict:
    return generate_strategy_advice()


@router.get("/api/strategy/latest")
def strategy_latest() -> dict:
    return generate_strategy_advice(persist=False)


@router.get("/api/strategy/config")
def strategy_config(_: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))]) -> dict:
    runtime = _read_runtime_settings()
    config = runtime.get("strategy_config") or {
        "high_price_threshold": 160,
        "low_price_threshold": 40,
        "soc_upper": 90,
        "soc_lower": 20,
        "charge_power": 80,
        "discharge_power": 80,
        "risk_threshold": 0.5,
        "auto_suggestion": True,
    }
    return response(config, data_source="runtime_config")


@router.post("/api/strategy/config")
def strategy_config_save(
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    result = save_system_config({"strategy_config": payload}, user=user, ip_address=request.client.host if request.client else "")
    return response(result.get("runtime", {}).get("strategy_config", payload), data_source="runtime_config")


@router.post("/api/strategy/reviews")
def strategy_review_save(
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    write_audit_log(
        action="strategy.review_save",
        user=user,
        resource_type="strategy_review",
        resource_id=str(payload.get("id") or payload.get("period") or ""),
        ip_address=request.client.host if request.client else "",
        metadata=payload,
    )
    return response({"saved": True, "review": payload}, data_source="audit_logs")


@router.get("/api/strategy/{run_id}")
def strategy_by_run(run_id: str) -> dict:
    return generate_strategy_advice(run_id=run_id, persist=False)


@router.post("/api/anomaly/explain")
def anomaly_explain(_: Annotated[CurrentUser, Depends(require_permission("task:run"))]) -> dict:
    return generate_anomaly_explanations()


@router.get("/api/anomaly/latest")
def anomaly_latest() -> dict:
    return generate_anomaly_explanations(persist=False)


@router.get("/api/anomaly/{run_id}")
def anomaly_by_run(run_id: str) -> dict:
    return generate_anomaly_explanations(run_id=run_id, persist=False)
