from __future__ import annotations

from typing import Any

import pandas as pd

from ...data_access import jsonable, price_column
from ...source_contract import attach_source_meta, resolve_forecast_source


def _money(value: Any) -> str:
    try:
        return f"{float(value):.2f} USD/MWh"
    except Exception:
        return "-"


def _forecast_df(run_id: str = "latest") -> tuple[dict[str, Any], pd.DataFrame, str | None]:
    run, rows, meta = resolve_forecast_source(run_id)
    payload = attach_source_meta({"available": bool(rows), "run_id": run.get("run_id"), "records": rows}, meta)
    df = pd.DataFrame(rows)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    pcol = price_column(df) if not df.empty else None
    if pcol:
        df["__price"] = pd.to_numeric(df[pcol], errors="coerce")
    return payload, df, pcol


def _time_text(value: Any) -> str:
    dt = pd.to_datetime(value, errors="coerce")
    return dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else ""


def _select_row(df: pd.DataFrame, target_time: str | None, mode: str, hour: int | None = None) -> pd.Series:
    if target_time and "datetime" in df.columns:
        target = pd.to_datetime(target_time, errors="coerce")
        if pd.notna(target):
            matched = df[df["datetime"].dt.strftime("%Y-%m-%d %H:%M") == target.strftime("%Y-%m-%d %H:%M")]
            if not matched.empty:
                return matched.iloc[0]
    if hour is not None and "datetime" in df.columns:
        matched = df[df["datetime"].dt.hour == int(hour)]
        if not matched.empty:
            return matched.iloc[0]
    prices = pd.to_numeric(df["__price"], errors="coerce")
    return df.loc[prices.idxmin() if mode == "low" else prices.idxmax()]


def get_forecast_metrics(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    payload, df, pcol = _forecast_df(run_id)
    if df.empty or not pcol:
        return {"tool": "get_forecast_metrics", "available": False, "message": "当前系统未查询到可用预测数据。"}
    prices = pd.to_numeric(df["__price"], errors="coerce")
    max_row = df.loc[prices.idxmax()]
    min_row = df.loc[prices.idxmin()]
    return jsonable(
        {
            "tool": "get_forecast_metrics",
            "available": True,
            "run_id": payload.get("run_id"),
            "avg_price": float(prices.mean()),
            "max_price": float(prices.max()),
            "max_time": _time_text(max_row.get("datetime")),
            "min_price": float(prices.min()),
            "min_time": _time_text(min_row.get("datetime")),
            "spread": float(prices.max() - prices.min()),
            "p25": float(prices.quantile(0.25)),
            "p75": float(prices.quantile(0.75)),
            "generated_at": (payload.get("meta") or {}).get("generated_at"),
            "evidence": [{"table": "forecast_results", "run_id": payload.get("run_id"), "fields": ["forecast_time", pcol, "risk_level"]}],
        }
    )


def explain_low_price_hour(target_time: str | None = None, hour: int | None = None, run_id: str = "latest", **_: Any) -> dict[str, Any]:
    payload, df, pcol = _forecast_df(run_id)
    if df.empty or not pcol:
        return {"tool": "explain_low_price_hour", "available": False, "message": "当前系统未查询到可用预测数据。"}
    prices = pd.to_numeric(df["__price"], errors="coerce")
    row = _select_row(df, target_time, "low", hour=hour)
    price = float(row.get("__price") or 0)
    avg = float(prices.mean())
    p25 = float(prices.quantile(0.25))
    hour = pd.to_datetime(row.get("datetime"), errors="coerce").hour if pd.notna(row.get("datetime")) else None
    reasons = [
        "预测电价低于未来24小时均价" if price < avg else "预测电价接近未来24小时低位",
        "预测电价位于未来24小时低分位" if price <= p25 else "预测电价不高于主要高价窗口",
    ]
    if hour is not None and hour <= 6:
        reasons.insert(0, "该时段处于凌晨非高峰区间")
    if str(row.get("risk_level") or "").lower() in {"low", "低", "低风险", ""}:
        reasons.append("系统未识别到明显高价风险信号")
    return jsonable(
        {
            "tool": "explain_low_price_hour",
            "available": True,
            "run_id": payload.get("run_id"),
            "time": _time_text(row.get("datetime")),
            "predicted_price": price,
            "avg_price": avg,
            "p25": p25,
            "risk_level": row.get("risk_level") or "low",
            "is_peak_hour": bool(row.get("is_peak_hour")),
            "possible_reasons": reasons,
            "advice": "可作为低价采购或储能充电参考窗口，但仍需结合实时市场复核。",
            "generated_at": (payload.get("meta") or {}).get("generated_at"),
            "evidence": [{"table": "forecast_results", "run_id": payload.get("run_id"), "time": _time_text(row.get("datetime"))}],
        }
    )


def explain_high_price_hour(target_time: str | None = None, hour: int | None = None, run_id: str = "latest", **_: Any) -> dict[str, Any]:
    payload, df, pcol = _forecast_df(run_id)
    if df.empty or not pcol:
        return {"tool": "explain_high_price_hour", "available": False, "message": "当前系统未查询到可用预测数据。"}
    prices = pd.to_numeric(df["__price"], errors="coerce")
    row = _select_row(df, target_time, "high", hour=hour)
    price = float(row.get("__price") or 0)
    avg = float(prices.mean())
    p75 = float(prices.quantile(0.75))
    rank = int(prices.rank(ascending=False, method="min").loc[row.name])
    reasons = []
    if price >= p75:
        reasons.append("预测电价高于未来24小时P75高价阈值")
    if bool(row.get("is_peak_hour")):
        reasons.append("该时段被系统标记为高峰小时")
    if row.get("forecast_load") is not None:
        reasons.append("负荷预测值需要重点复核")
    if row.get("spike_risk_prob") is not None:
        reasons.append("尖峰风险概率纳入高价风险判断")
    return jsonable(
        {
            "tool": "explain_high_price_hour",
            "available": True,
            "run_id": payload.get("run_id"),
            "time": _time_text(row.get("datetime")),
            "predicted_price": price,
            "avg_price": avg,
            "p75": p75,
            "rank": rank,
            "risk_level": row.get("risk_level") or "medium",
            "forecast_load": row.get("forecast_load"),
            "temperature": row.get("temperature"),
            "spike_risk_prob": row.get("spike_risk_prob"),
            "possible_reasons": reasons or ["该时段预测价格处于相对高位，需要结合实时市场和负荷变化复核"],
            "advice": "建议复核售电敞口、负荷预测、实时市场变化和合同约束，不应直接自动执行交易。",
            "generated_at": (payload.get("meta") or {}).get("generated_at"),
            "evidence": [{"table": "forecast_results", "run_id": payload.get("run_id"), "time": _time_text(row.get("datetime"))}],
        }
    )
