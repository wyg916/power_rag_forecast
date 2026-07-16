from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from ....core.security import CurrentUser, require_permission
from ....data_access import dashboard_summary, load_latest_forecast
from ....repositories.forecast_repository import (
    get_forecast_run,
    latest_successful_run,
    list_forecast_runs,
    load_forecast_results,
)
from ....repositories.audit_repository import write_audit_log
from ....services.dashboard_home_service import dashboard_kpi_payload, forecast_24h_payload, risk_summary_payload
from ....workers.dispatcher import enqueue_task
from ....schemas import ForecastRunRequest
from ....source_contract import (
    SourceType,
    attach_source_meta,
    forecast_context_payload,
    resolve_forecast_source,
    source_meta,
)
from ....stage1_services import (
    load_forecast,
    market_history,
    model_explain,
    prediction_detail,
    prediction_latest,
    renewable_forecast,
    risk_level,
    weather_forecast,
)
from ....task_manager import task_manager


router = APIRouter()


def _with_latest_meta(payload: dict, *, derived: bool = False) -> dict:
    _, _, meta = resolve_forecast_source("latest")
    if derived and meta.get("source_type") in {"real", "historical"}:
        meta = {
            **meta,
            "source_type": SourceType.DERIVED.value,
            "evidence": list(meta.get("evidence") or []) + [{"derivation": "api_projection"}],
        }
    return attach_source_meta(payload, meta)


@router.get("/api/dashboard/summary")
def dashboard() -> dict:
    return _with_latest_meta(dashboard_summary(), derived=True)


@router.get("/api/dashboard/kpi")
def dashboard_kpi() -> dict:
    return _with_latest_meta(dashboard_kpi_payload(), derived=True)


@router.get("/api/risk/summary")
def risk_summary() -> dict:
    return _with_latest_meta(risk_summary_payload(), derived=True)


@router.post("/api/forecast/run")
def run_forecast(
    payload: ForecastRunRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("forecast:run"))],
) -> dict:
    mapping = {
        "fast_forecast": "fast_forecast",
        "refresh_fast_forecast": "today_analysis",
        "retrain_model": "retrain_model",
    }
    result = enqueue_task(mapping[payload.mode])
    write_audit_log(
        action="forecast.run",
        user=user,
        resource_type="forecast",
        resource_id=str(result.get("task_id") or result.get("run_id") or payload.mode),
        ip_address=request.client.host if request.client else "",
        metadata={"mode": payload.mode, "task": result},
    )
    return result


@router.get("/api/forecast/latest")
def latest_forecast() -> dict:
    return load_latest_forecast()


@router.get("/api/forecast/runs")
def forecast_runs(status: str | None = None, limit: int = 50) -> dict:
    items = list_forecast_runs(status=status, limit=limit)
    meta = source_meta(
        SourceType.HISTORICAL if items else SourceType.UNAVAILABLE,
        "electricity_day_ahead_price",
        generated_at=items[0].get("finished_at") or items[0].get("created_at") if items else None,
        evidence=[{"table": "forecast_runs", "record_count": len(items)}],
        unavailable_reason=None if items else "no_forecast_runs",
    )
    return attach_source_meta({"available": bool(items), "items": items}, meta)


@router.get("/api/forecast/runs/latest-success")
def forecast_latest_success() -> dict:
    context = forecast_context_payload("latest")
    if not context.get("available"):
        context["message"] = "暂无成功且恰好包含 24 行结果的预测批次。"
        return context
    run = latest_successful_run()
    return attach_source_meta({"available": True, "run": run}, context["meta"])


@router.get("/api/forecast/runs/{run_id}")
def forecast_run_detail(run_id: str) -> dict:
    run, _, meta = resolve_forecast_source(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="预测批次不存在")
    return attach_source_meta({"available": meta.get("source_type") != "unavailable", "run": run}, meta)


@router.get("/api/forecast/runs/{run_id}/results")
def forecast_run_results(run_id: str) -> dict:
    run, rows, meta = resolve_forecast_source(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="预测批次不存在")
    return attach_source_meta(
        {
            "available": bool(rows),
            "run_id": run_id,
            "status": run.get("status"),
            "record_count": len(rows),
            "model_version": run.get("model_version"),
            "feature_version": run.get("feature_version"),
            "generated_at": run.get("finished_at") or run.get("created_at"),
            "records": rows,
        },
        meta,
    )


@router.get("/api/source/context")
def source_context(
    domain: str = "electricity_day_ahead_price",
    run_id: str = "latest",
) -> dict:
    try:
        return forecast_context_payload(run_id, domain=domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="不支持的数据域；不会自动猜测或跨域回退。") from exc


@router.get("/api/forecast/24h")
def forecast_24h() -> dict:
    return _with_latest_meta(forecast_24h_payload(), derived=True)


@router.get("/api/prediction/latest")
def stage1_prediction_latest(market: str | None = None, date: str | None = None) -> dict:
    return prediction_latest(market=market, date=date)


@router.get("/api/prediction/detail")
def stage1_prediction_detail(market: str | None = None, date: str | None = None) -> dict:
    return prediction_detail(market=market, date=date)


@router.get("/api/market/history")
def stage1_market_history(market: str | None = None, start: str | None = None, end: str | None = None) -> dict:
    return market_history(market=market, start=start, end=end)


@router.get("/api/weather/forecast")
def stage1_weather_forecast(city: str | None = None, date: str | None = None) -> dict:
    return weather_forecast(city=city, date=date)


@router.get("/api/load/forecast")
def stage1_load_forecast(market: str | None = None, date: str | None = None) -> dict:
    return load_forecast(market=market, date=date)


@router.get("/api/renewable/forecast")
def stage1_renewable_forecast(market: str | None = None, date: str | None = None) -> dict:
    return renewable_forecast(market=market, date=date)


@router.get("/api/model/explain")
def stage1_model_explain(market: str | None = None, date: str | None = None) -> dict:
    return model_explain(market=market, date=date)


@router.get("/api/risk/level")
def stage1_risk_level(market: str | None = None, date: str | None = None) -> dict:
    return risk_level(market=market, date=date)


@router.get("/api/forecast/{run_id}")
def forecast_by_run(run_id: str) -> dict:
    if run_id == "latest":
        return load_latest_forecast()
    run, rows, meta = resolve_forecast_source(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="预测批次不存在")
    return attach_source_meta(
        {
            "run_id": run_id,
            "status": run.get("status"),
            "available": bool(rows),
            "source": "postgresql.forecast_runs",
            "generated_at": run.get("finished_at") or run.get("created_at"),
            "model_version": run.get("model_version"),
            "feature_version": run.get("feature_version"),
            "result_hash": run.get("result_hash"),
            "summary": {},
            "records": rows,
        },
        meta,
    )


@router.get("/api/forecast/{run_id}/hour/{hour}")
def forecast_hour(run_id: str, hour: str) -> dict:
    payload = forecast_by_run(run_id)
    rows = payload.get("records") or []
    if not rows:
        raise HTTPException(status_code=404, detail="暂无预测数据")
    matched = []
    for row in rows:
        dt = str(row.get("datetime") or "")
        if dt.endswith(f" {hour}:00:00") or dt.endswith(f" {hour}:00") or dt[11:13] == hour.zfill(2):
            matched.append(row)
    if not matched:
        raise HTTPException(status_code=404, detail="未找到该小时预测数据")
    return attach_source_meta(
        {"run_id": payload.get("run_id"), "hour": hour, "records": matched},
        payload.get("meta") or source_meta(SourceType.UNAVAILABLE, "electricity_day_ahead_price", unavailable_reason="meta_missing"),
    )
