from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ....core.security import CurrentUser, require_permission
from ....platform_services import generate_anomaly_explanations, generate_strategy_advice
from ....repositories.base import postgres_engine
from ....repositories.strategy_repository import get_strategy, list_strategies, list_strategy_reviews, transition_strategy
from ....repositories.strategy_runtime_repository import get_strategy_runtime_facts
from ....schemas import StrategyActionRequest, StrategyGenerateRequest
from ....services.strategy_governance_service import (
    StrategyGovernanceError,
    generate_strategy_draft,
    rule_inventory,
)
from ....repositories.audit_repository import write_audit_log
from ....services.dashboard_home_service import strategy_today_payload
from ....services.ui_platform_service import _read_runtime_settings, response, save_system_config
from ....source_contract import SourceType, attach_source_meta, resolve_forecast_source, source_meta


router = APIRouter()


def _with_strategy_meta(payload: dict) -> dict:
    _, _, base = resolve_forecast_source(payload.get("run_id") or "latest")
    if base.get("source_type") in {"real", "historical"}:
        base = {
            **base,
            "source_type": SourceType.DERIVED.value,
            "domain": "strategy",
            "evidence": list(base.get("evidence") or []) + [{"derivation": "strategy_read"}],
        }
    else:
        base = source_meta(
            SourceType.UNAVAILABLE,
            "strategy",
            run_id=base.get("run_id"),
            unavailable_reason=base.get("unavailable_reason") or "forecast_unavailable",
        )
    return attach_source_meta(payload, base)


def _strategy_engine():
    engine = postgres_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="策略数据库不可用")
    return engine


def _strategy_error(exc: StrategyGovernanceError) -> HTTPException:
    detail = str(exc)
    if "not_found" in detail:
        return HTTPException(status_code=404, detail=detail)
    if "conflict" in detail or "illegal_strategy_transition" in detail:
        return HTTPException(status_code=409, detail=detail)
    if "database_unavailable" in detail:
        return HTTPException(status_code=503, detail=detail)
    return HTTPException(status_code=422, detail=detail)


def _governed_action(strategy_id: str, action: str, payload: StrategyActionRequest, user: CurrentUser) -> dict:
    try:
        return transition_strategy(
            strategy_id,
            action,
            request_id=payload.request_id,
            comment=payload.review_comment,
            user=user,
            engine=_strategy_engine(),
        )
    except StrategyGovernanceError as exc:
        raise _strategy_error(exc) from exc


@router.post("/api/strategies/generate")
def governed_strategy_generate(
    payload: StrategyGenerateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("strategy:generate"))],
) -> dict:
    try:
        return generate_strategy_draft(
            payload.run_id,
            payload.report_id,
            created_by=user.username,
            engine=_strategy_engine(),
        )
    except StrategyGovernanceError as exc:
        raise _strategy_error(exc) from exc


@router.get("/api/strategies")
def governed_strategy_list(
    _: Annotated[CurrentUser, Depends(require_permission("strategy:read"))],
    run_id: str = Query(default="", max_length=96),
    report_id: str = Query(default="", max_length=96),
    status_value: str = Query(default="", alias="status", max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return list_strategies(run_id=run_id, report_id=report_id, status=status_value, limit=limit, offset=offset, engine=_strategy_engine())


@router.get("/api/strategies/latest")
def governed_strategy_latest(
    _: Annotated[CurrentUser, Depends(require_permission("strategy:read"))],
) -> dict:
    payload = list_strategies(limit=1, engine=_strategy_engine())
    return payload["items"][0] if payload["items"] else {"available": False, "unavailable_reason": "strategy_not_found"}


@router.get("/api/strategies/rules")
def governed_strategy_rules(
    _: Annotated[CurrentUser, Depends(require_permission("strategy:read"))],
) -> dict:
    return {"items": rule_inventory(), "total": len(rule_inventory())}


@router.get("/api/strategies/{strategy_id}")
def governed_strategy_detail(
    strategy_id: str,
    _: Annotated[CurrentUser, Depends(require_permission("strategy:read"))],
) -> dict:
    item = get_strategy(strategy_id, engine=_strategy_engine())
    if not item:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    return item


@router.get("/api/strategies/{strategy_id}/evidence")
def governed_strategy_evidence(
    strategy_id: str,
    _: Annotated[CurrentUser, Depends(require_permission("strategy:read"))],
) -> dict:
    item = get_strategy(strategy_id, engine=_strategy_engine())
    if not item:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    return {"strategy_id": strategy_id, "content_hash": item.get("content_hash"), "evidence": item.get("evidence_json") or {}}


@router.get("/api/strategies/{strategy_id}/reviews")
def governed_strategy_reviews(
    strategy_id: str,
    _: Annotated[CurrentUser, Depends(require_permission("strategy:read"))],
) -> dict:
    if not get_strategy(strategy_id, engine=_strategy_engine()):
        raise HTTPException(status_code=404, detail="strategy_not_found")
    items = list_strategy_reviews(strategy_id, engine=_strategy_engine())
    return {"items": items, "total": len(items)}


@router.post("/api/strategies/{strategy_id}/submit")
def governed_strategy_submit(
    strategy_id: str,
    payload: StrategyActionRequest,
    user: Annotated[CurrentUser, Depends(require_permission("strategy:submit"))],
) -> dict:
    return _governed_action(strategy_id, "submit", payload, user)


@router.post("/api/strategies/{strategy_id}/approve")
def governed_strategy_approve(strategy_id: str, payload: StrategyActionRequest, user: Annotated[CurrentUser, Depends(require_permission("strategy:review"))]) -> dict:
    return _governed_action(strategy_id, "approve", payload, user)


@router.post("/api/strategies/{strategy_id}/reject")
def governed_strategy_reject(strategy_id: str, payload: StrategyActionRequest, user: Annotated[CurrentUser, Depends(require_permission("strategy:review"))]) -> dict:
    return _governed_action(strategy_id, "reject", payload, user)


@router.post("/api/strategies/{strategy_id}/return")
def governed_strategy_return(strategy_id: str, payload: StrategyActionRequest, user: Annotated[CurrentUser, Depends(require_permission("strategy:review"))]) -> dict:
    return _governed_action(strategy_id, "return", payload, user)


@router.post("/api/strategies/{strategy_id}/publish")
def governed_strategy_publish(strategy_id: str, payload: StrategyActionRequest, user: Annotated[CurrentUser, Depends(require_permission("strategy:publish"))]) -> dict:
    return _governed_action(strategy_id, "publish", payload, user)


@router.post("/api/strategies/{strategy_id}/{action}")
def governed_strategy_admin_action(
    strategy_id: str,
    action: str,
    payload: StrategyActionRequest,
    user: Annotated[CurrentUser, Depends(require_permission("strategy:publish"))],
) -> dict:
    if action not in {"supersede", "expire", "cancel"}:
        raise HTTPException(status_code=404, detail="strategy_action_not_found")
    return _governed_action(strategy_id, action, payload, user)


@router.post("/api/strategy/generate")
def strategy_generate(
    payload: StrategyGenerateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("strategy:generate"))],
) -> dict:
    return governed_strategy_generate(payload, user)


@router.get("/api/strategy/latest")
def strategy_latest() -> dict:
    return _with_strategy_meta(generate_strategy_advice(persist=False))


@router.get("/api/strategy/today")
def strategy_today() -> dict:
    return _with_strategy_meta(strategy_today_payload())


@router.get("/api/strategy/runtime-facts")
def strategy_runtime_facts(
    _: Annotated[CurrentUser, Depends(require_permission("strategy:read"))],
) -> dict:
    try:
        return get_strategy_runtime_facts(engine=_strategy_engine())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/strategy/config")
def strategy_config(_: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))]) -> dict:
    runtime = _read_runtime_settings()
    defaults = {
        "high_price_threshold": 160,
        "low_price_threshold": 40,
        "soc_upper": 90,
        "soc_lower": 20,
        "charge_power": 80,
        "discharge_power": 80,
        "risk_threshold": 0.5,
        "auto_suggestion": True,
    }
    config = {**defaults, **(runtime.get("strategy_config") or {})}
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
    return _with_strategy_meta(generate_strategy_advice(run_id=run_id, persist=False))


@router.post("/api/anomaly/explain")
def anomaly_explain(_: Annotated[CurrentUser, Depends(require_permission("task:run"))]) -> dict:
    return generate_anomaly_explanations()


@router.get("/api/anomaly/latest")
def anomaly_latest() -> dict:
    return _with_strategy_meta(generate_anomaly_explanations(persist=False))


@router.get("/api/anomaly/{run_id}")
def anomaly_by_run(run_id: str) -> dict:
    return _with_strategy_meta(generate_anomaly_explanations(run_id=run_id, persist=False))
