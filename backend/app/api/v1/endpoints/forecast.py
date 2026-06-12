from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from ....core.security import CurrentUser, require_permission
from ....data_access import dashboard_summary, load_latest_forecast
from ....repositories.audit_repository import write_audit_log
from ....workers.dispatcher import enqueue_task
from ....schemas import ForecastRunRequest
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


@router.get("/api/dashboard/summary")
def dashboard() -> dict:
    return dashboard_summary()


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
    payload = load_latest_forecast()
    if run_id != "latest" and run_id != payload.get("run_id"):
        payload["message"] = "当前本地文件只保留最新预测明细；历史 run_id 请从数据库或归档目录查询。"
    return payload


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
    return {"run_id": payload.get("run_id"), "hour": hour, "records": matched}
