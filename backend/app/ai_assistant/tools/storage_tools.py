from __future__ import annotations

from typing import Any

import pandas as pd

from ...data_access import jsonable, price_column
from ...source_contract import attach_source_meta, resolve_forecast_source


def _df(run_id: str = "latest") -> tuple[dict[str, Any], pd.DataFrame, str | None]:
    run, rows, meta = resolve_forecast_source(run_id)
    payload = attach_source_meta({"available": bool(rows), "run_id": run.get("run_id"), "records": rows}, meta)
    df = pd.DataFrame(rows)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    pcol = price_column(df) if not df.empty else None
    if pcol:
        df["__price"] = pd.to_numeric(df[pcol], errors="coerce")
    return payload, df, pcol


def _hour(row: pd.Series) -> str:
    dt = pd.to_datetime(row.get("datetime"), errors="coerce")
    return dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else ""


def _window(row: pd.Series, reason: str) -> dict[str, Any]:
    return {
        "time": _hour(row),
        "predicted_price": float(row.get("__price") or 0),
        "risk_level": row.get("risk_level") or "low",
        "reason": reason,
    }


def get_storage_discharge_windows(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    payload, df, pcol = _df(run_id)
    if df.empty or not pcol:
        return {"tool": "get_storage_discharge_windows", "available": False, "message": "当前系统未查询到可用预测数据。"}
    prices = pd.to_numeric(df["__price"], errors="coerce")
    p75 = float(prices.quantile(0.75))
    p25 = float(prices.quantile(0.25))
    high = df.loc[prices[prices >= p75].sort_values(ascending=False).index].head(5)
    low = df.loc[prices[prices <= p25].sort_values(ascending=True).index].head(5)
    return jsonable(
        {
            "tool": "get_storage_discharge_windows",
            "available": True,
            "run_id": payload.get("run_id") or run_id,
            "recommended_discharge_hours": [_window(row, "高价放电候选窗口") for _, row in high.iterrows()],
            "charge_reference_hours": [_window(row, "低价充电参考窗口") for _, row in low.iterrows()],
            "avg_price": float(prices.mean()),
            "spread": float(prices.max() - prices.min()),
            "p75": p75,
            "p25": p25,
            "strategy_note": "可作为低充高放参考，需要结合SOC、容量、效率和实时市场复核。",
            "generated_at": (payload.get("meta") or {}).get("generated_at"),
            "evidence": [{"table": "forecast_results", "run_id": payload.get("run_id"), "fields": ["forecast_time", pcol, "risk_level"]}],
        }
    )


def get_storage_charge_windows(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    payload, df, pcol = _df(run_id)
    if df.empty or not pcol:
        return {"tool": "get_storage_charge_windows", "available": False, "message": "当前系统未查询到可用预测数据。"}
    prices = pd.to_numeric(df["__price"], errors="coerce")
    p75 = float(prices.quantile(0.75))
    p25 = float(prices.quantile(0.25))
    low = df.loc[prices[prices <= p25].sort_values(ascending=True).index].head(5)
    high = df.loc[prices[prices >= p75].sort_values(ascending=False).index].head(5)
    return jsonable(
        {
            "tool": "get_storage_charge_windows",
            "available": True,
            "run_id": payload.get("run_id") or run_id,
            "recommended_charge_hours": [_window(row, "低价充电候选窗口") for _, row in low.iterrows()],
            "discharge_reference_hours": [_window(row, "高价放电参考窗口") for _, row in high.iterrows()],
            "avg_price": float(prices.mean()),
            "spread": float(prices.max() - prices.min()),
            "p75": p75,
            "p25": p25,
            "strategy_note": "充电窗口应结合SOC、容量、效率和后续放电价差复核。",
            "generated_at": (payload.get("meta") or {}).get("generated_at"),
            "evidence": [{"table": "forecast_results", "run_id": payload.get("run_id"), "fields": ["forecast_time", pcol, "risk_level"]}],
        }
    )
