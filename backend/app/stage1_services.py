from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .core.config import get_settings
from .config import project_config, project_paths
from .data_access import (
    jsonable,
    load_latest_forecast,
    model_status,
    price_column,
    query_dataframe,
    read_excel_safe,
    records,
    risk_probability_column,
)
from .repositories.feature_repository import load_feature_importance_from_postgres
from .repositories.load_repository import load_forecast_load_from_postgres
from .repositories.market_data_repository import load_market_history_from_postgres
from .repositories.weather_repository import load_weather_forecast_from_postgres


def _legacy_fallback_allowed() -> bool:
    settings = get_settings()
    return bool(settings.database_allow_legacy_fallback or not settings.has_database_url)


def _frame_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows or [])


def _configured_market() -> str:
    market = project_config().get("market", {}) or {}
    return str(market.get("pjm_node_name") or market.get("pjm_region") or "DOM")


def _normalize_market(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _market_note(requested: str | None) -> tuple[str, bool, str]:
    actual = _configured_market()
    if not requested:
        return actual, True, ""
    req = str(requested).strip()
    matched = _normalize_market(req) in {
        _normalize_market(actual),
        "pjm",
        "dom",
        "当前市场",
        "默认市场",
    }
    if matched:
        return actual, True, ""
    return actual, False, f"当前系统未查询到 {req} 专属数据；系统当前可用市场为 {actual}。"


def _date_text(value: str | None) -> str:
    if not value:
        return ""
    dt = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(dt) else dt.strftime("%Y-%m-%d")


def _price_stats(df: pd.DataFrame, pcol: str) -> dict[str, Any]:
    price = pd.to_numeric(df[pcol], errors="coerce")
    if not price.notna().any():
        return {}
    max_row = df.loc[price.idxmax()]
    min_row = df.loc[price.idxmin()]
    return {
        "avg_price_pred": float(price.mean()),
        "peak_price_pred": float(price.max()),
        "valley_price_pred": float(price.min()),
        "peak_hour": _fmt_time(max_row.get("datetime")),
        "valley_hour": _fmt_time(min_row.get("datetime")),
        "peak_valley_spread": float(price.max() - price.min()),
    }


def _fmt_time(value: Any) -> str:
    dt = pd.to_datetime(value, errors="coerce")
    return dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else ""


def _fmt_period(value: Any) -> str:
    dt = pd.to_datetime(value, errors="coerce")
    return dt.strftime("%H:%M") if pd.notna(dt) else ""


def _risk_summary(df: pd.DataFrame, pcol: str) -> dict[str, Any]:
    price = pd.to_numeric(df[pcol], errors="coerce")
    prob_col = risk_probability_column(df)
    prob = pd.to_numeric(df[prob_col], errors="coerce").fillna(0) if prob_col else pd.Series([0.0] * len(df), index=df.index)
    p75 = float(price.quantile(0.75)) if price.notna().any() else 0.0
    risk_rows = df[(prob >= 0.5) | (price >= p75)]
    if "is_peak_hour" in df.columns:
        peak_rows = df[pd.to_numeric(df["is_peak_hour"], errors="coerce").fillna(0).astype(int) == 1]
        risk_rows = pd.concat([risk_rows, peak_rows]).drop_duplicates()
    risk_rows = risk_rows.copy()
    if not risk_rows.empty:
        risk_rows["__price"] = pd.to_numeric(risk_rows[pcol], errors="coerce").fillna(0)
        if prob_col:
            risk_rows["__prob"] = pd.to_numeric(risk_rows[prob_col], errors="coerce").fillna(0)
        else:
            risk_rows["__prob"] = 0.0
        risk_rows = risk_rows.sort_values(["__prob", "__price"], ascending=False).head(6)
    max_prob = float(prob.max()) if len(prob) else 0.0
    high_count = int((prob >= 0.5).sum())
    risk_level = "高" if high_count >= 3 or max_prob >= 0.8 else ("中高" if high_count or max_prob >= 0.5 else ("中" if price.max() >= p75 else "低"))
    return {
        "risk_level": risk_level,
        "max_spike_probability": max_prob,
        "focus_periods": [_fmt_period(v) for v in risk_rows.get("datetime", pd.Series(dtype=object)).tolist() if _fmt_period(v)],
        "risk_count": high_count,
        "p75_price": p75,
    }


def _feature_importance(limit: int = 5) -> list[dict[str, Any]]:
    postgres_rows = load_feature_importance_from_postgres(limit=max(limit, 20))
    if postgres_rows:
        return records(pd.DataFrame(postgres_rows).head(limit))
    path = project_paths().result_table_dir / "13_特征重要性.xlsx"
    df = read_excel_safe(path)
    if df.empty:
        return []
    value_col = next((c for c in df.columns if "重要" in str(c) or "importance" in str(c).lower()), None)
    name_col = next((c for c in df.columns if c != value_col), None)
    if not value_col or not name_col:
        return records(df.head(limit))
    work = df[[name_col, value_col]].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.sort_values(value_col, ascending=False).head(limit)
    return [{"feature": str(row[name_col]), "importance": row[value_col]} for _, row in work.iterrows()]


def _main_factors(df: pd.DataFrame, pcol: str) -> list[str]:
    factors: list[str] = []
    risk = _risk_summary(df, pcol)
    if risk["risk_level"] in {"中高", "高"}:
        factors.append("高价或尖峰风险时段集中，需要重点复核")
    if "forecast_load" in df.columns:
        load = pd.to_numeric(df["forecast_load"], errors="coerce")
        if load.notna().any():
            high_load = df.loc[load >= load.quantile(0.75)]
            if not high_load.empty:
                factors.append("预测负荷存在高位时段，可能抬升高峰电价")
    if "future_weather_source" in df.columns and df["future_weather_source"].astype(str).str.contains("代理|历史", na=False).any():
        factors.append("天气数据含历史代理口径，实际天气偏差需要人工关注")
    if "预测区间宽度" in df.columns:
        width = pd.to_numeric(df["预测区间宽度"], errors="coerce")
        if width.notna().any() and float(width.max()) > float(width.quantile(0.75)):
            factors.append("部分小时预测区间较宽，价格不确定性偏高")
    importance = _feature_importance(3)
    if importance:
        factors.append("模型主要参考特征包括：" + "、".join(str(item.get("feature")) for item in importance[:3]))
    return factors[:6] or ["当前预测主要基于历史价格、负荷、天气和时序特征综合判断"]


def _model_confidence() -> float | None:
    active = model_status().get("active") or {}
    rmse = active.get("test_rmse")
    try:
        rmse_value = float(rmse)
    except Exception:
        return None
    return round(max(0.05, min(0.95, 1 - rmse_value / 100)), 2)


def prediction_latest(market: str | None = None, date: str | None = None) -> dict[str, Any]:
    actual_market, market_matched, market_message = _market_note(market)
    payload = load_latest_forecast()
    rows = payload.get("records") or []
    df = pd.DataFrame(rows)
    if df.empty:
        empty_message = str(payload.get("message") or "当前系统未查询到可用预测结果。")
        return {
            "available": False,
            "market": actual_market,
            "requested_market": market,
            "market_matched": market_matched,
            "message": market_message or empty_message,
            "messages": [item for item in (market_message, empty_message) if item],
            "run_id": payload.get("run_id"),
            "source": payload.get("source"),
            "source_type": payload.get("source_type"),
        }
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    pcol = price_column(df)
    if not pcol:
        missing_price_message = "当前预测结果缺少可识别的电价字段。"
        return {
            "available": False,
            "market": actual_market,
            "requested_market": market,
            "market_matched": market_matched,
            "message": missing_price_message,
            "messages": [item for item in (market_message, missing_price_message) if item],
            "run_id": payload.get("run_id"),
            "source": payload.get("source"),
            "source_type": payload.get("source_type"),
        }

    requested_date = _date_text(date)
    date_matched = True
    date_message = ""
    matched_df = df
    if requested_date:
        strict = df[df["datetime"].dt.strftime("%Y-%m-%d") == requested_date]
        if strict.empty:
            date_matched = False
            date_message = f"当前系统未查询到 {requested_date} 的预测明细；以下返回系统最新预测窗口。"
        else:
            matched_df = strict

    stats = _price_stats(matched_df, pcol)
    risk = _risk_summary(matched_df, pcol)
    start = pd.to_datetime(matched_df["datetime"], errors="coerce").min()
    end = pd.to_datetime(matched_df["datetime"], errors="coerce").max()
    result = {
        "available": True,
        "market": actual_market,
        "requested_market": market or actual_market,
        "market_matched": market_matched,
        "date": requested_date or (start.strftime("%Y-%m-%d") if pd.notna(start) else ""),
        "requested_date": requested_date,
        "date_matched": date_matched,
        "forecast_start": start,
        "forecast_end": end,
        "avg_price_pred": stats.get("avg_price_pred"),
        "peak_price_pred": stats.get("peak_price_pred"),
        "valley_price_pred": stats.get("valley_price_pred"),
        "peak_hour": stats.get("peak_hour"),
        "valley_hour": stats.get("valley_hour"),
        "peak_valley_spread": stats.get("peak_valley_spread"),
        "risk_level": risk["risk_level"],
        "focus_periods": risk["focus_periods"],
        "main_factors": _main_factors(matched_df, pcol),
        "model_confidence": _model_confidence(),
        "price_column": pcol,
        "records": records(matched_df),
        "messages": [m for m in [market_message, date_message] if m],
        "run_id": payload.get("run_id"),
        "source": payload.get("source"),
        "source_type": payload.get("source_type"),
    }
    return jsonable(result)


def prediction_detail(market: str | None = None, date: str | None = None) -> dict[str, Any]:
    requested_date = _date_text(date)
    latest = prediction_latest(market=market, date=requested_date)
    if requested_date and not latest.get("date_matched", True):
        return {
            "available": False,
            "market": latest.get("market"),
            "requested_market": market,
            "date": requested_date,
            "message": f"当前系统未查询到 {requested_date} 的预测结果。",
            "latest_available_date": latest.get("date"),
        }
    return latest


def market_history(market: str | None = None, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    actual_market, market_matched, market_message = _market_note(market)
    postgres_rows = load_market_history_from_postgres(limit=5000)
    df = _frame_from_rows(postgres_rows)
    if df.empty and _legacy_fallback_allowed():
        df = query_dataframe("SELECT * FROM raw_da_price ORDER BY datetime DESC LIMIT 5000")
    if df.empty:
        df = read_excel_safe(project_paths().data_dir / "da_price_raw.xlsx")
    if df.empty:
        return {"available": False, "market": actual_market, "message": market_message or "当前系统未查询到历史电价数据。"}
    if "datetime" not in df.columns:
        return {"available": False, "market": actual_market, "message": "历史电价数据缺少 datetime 字段。"}
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    pcol = "da_price" if "da_price" in df.columns else price_column(df)
    if not pcol:
        return {"available": False, "market": actual_market, "message": "历史电价数据缺少价格字段。"}
    start_dt = pd.to_datetime(start, errors="coerce") if start else pd.NaT
    end_dt = pd.to_datetime(end, errors="coerce") if end else pd.NaT
    if pd.notna(start_dt):
        df = df[df["datetime"] >= start_dt]
    if pd.notna(end_dt):
        df = df[df["datetime"] < end_dt + pd.Timedelta(days=1)]
    df = df.sort_values("datetime")
    price = pd.to_numeric(df[pcol], errors="coerce")
    return jsonable(
        {
            "available": not df.empty,
            "market": actual_market,
            "requested_market": market or actual_market,
            "market_matched": market_matched,
            "message": market_message,
            "start": _fmt_time(df["datetime"].min()) if not df.empty else "",
            "end": _fmt_time(df["datetime"].max()) if not df.empty else "",
            "avg_price": float(price.mean()) if price.notna().any() else None,
            "max_price": float(price.max()) if price.notna().any() else None,
            "min_price": float(price.min()) if price.notna().any() else None,
            "records": records(df.tail(200)),
        }
    )


def weather_forecast(city: str | None = None, date: str | None = None) -> dict[str, Any]:
    paths = project_paths()
    df = _frame_from_rows(load_weather_forecast_from_postgres(limit=5000))
    if df.empty and _legacy_fallback_allowed():
        df = read_excel_safe(paths.data_dir / "weather_raw.xlsx")
    if df.empty:
        return {"available": False, "city": city or project_config().get("market", {}).get("weather_point_name"), "message": "当前系统未查询到天气数据。"}
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    requested_date = _date_text(date)
    matched = df[df["datetime"].dt.strftime("%Y-%m-%d") == requested_date] if requested_date else df.tail(24)
    date_matched = bool(not matched.empty)
    if matched.empty:
        matched = df.tail(24)
    temp_col = "temperature" if "temperature" in matched.columns else None
    temp = pd.to_numeric(matched[temp_col], errors="coerce") if temp_col else pd.Series(dtype=float)
    return jsonable(
        {
            "available": True,
            "city": city or project_config().get("market", {}).get("weather_point_name", ""),
            "date": requested_date or _date_text(matched["datetime"].max()),
            "date_matched": date_matched,
            "message": "" if date_matched or not requested_date else f"当前系统未查询到 {requested_date} 天气预测，返回最新天气数据作为参考。",
            "avg_temperature": float(temp.mean()) if temp.notna().any() else None,
            "max_temperature": float(temp.max()) if temp.notna().any() else None,
            "min_temperature": float(temp.min()) if temp.notna().any() else None,
            "records": records(matched),
        }
    )


def load_forecast(market: str | None = None, date: str | None = None) -> dict[str, Any]:
    actual_market, market_matched, market_message = _market_note(market)
    df = _frame_from_rows(load_forecast_load_from_postgres(limit=5000))
    if df.empty and _legacy_fallback_allowed():
        df = read_excel_safe(project_paths().data_dir / "forecast_load_selected.xlsx")
    if df.empty:
        return {"available": False, "market": actual_market, "message": market_message or "当前系统未查询到负荷预测数据。"}
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    requested_date = _date_text(date)
    matched = df[df["datetime"].dt.strftime("%Y-%m-%d") == requested_date] if requested_date else df.tail(24)
    date_matched = bool(not matched.empty)
    if matched.empty:
        matched = df.tail(24)
    col = "forecast_load" if "forecast_load" in matched.columns else next((c for c in matched.columns if "load" in str(c).lower() or "负荷" in str(c)), None)
    values = pd.to_numeric(matched[col], errors="coerce") if col else pd.Series(dtype=float)
    return jsonable(
        {
            "available": True,
            "market": actual_market,
            "requested_market": market or actual_market,
            "market_matched": market_matched,
            "date": requested_date or _date_text(matched["datetime"].max()),
            "date_matched": date_matched,
            "message": market_message or ("" if date_matched or not requested_date else f"当前系统未查询到 {requested_date} 负荷预测，返回最新负荷预测作为参考。"),
            "avg_load": float(values.mean()) if values.notna().any() else None,
            "max_load": float(values.max()) if values.notna().any() else None,
            "min_load": float(values.min()) if values.notna().any() else None,
            "records": records(matched),
        }
    )


def renewable_forecast(market: str | None = None, date: str | None = None) -> dict[str, Any]:
    actual_market, market_matched, market_message = _market_note(market)
    return {
        "available": False,
        "market": actual_market,
        "requested_market": market or actual_market,
        "market_matched": market_matched,
        "date": _date_text(date),
        "message": (market_message + " " if market_message else "") + "当前系统未接入新能源出力预测数据，以下只能做通用机理分析。",
    }


def model_explain(market: str | None = None, date: str | None = None) -> dict[str, Any]:
    active = model_status().get("active") or {}
    importance = _feature_importance(10)
    latest = prediction_latest(market=market, date=date)
    return jsonable(
        {
            "available": bool(active or importance),
            "market": latest.get("market") or _configured_market(),
            "date": latest.get("date") or _date_text(date),
            "active_model": active,
            "model_confidence": latest.get("model_confidence"),
            "feature_importance": importance,
            "main_factors": latest.get("main_factors") or [],
            "message": "模型解释基于当前 Active 模型登记信息、预测结果和特征重要性表。",
        }
    )


def risk_level(market: str | None = None, date: str | None = None) -> dict[str, Any]:
    latest = prediction_latest(market=market, date=date)
    return {
        "available": bool(latest.get("available")),
        "market": latest.get("market"),
        "date": latest.get("date"),
        "risk_level": latest.get("risk_level"),
        "focus_periods": latest.get("focus_periods") or [],
        "main_factors": latest.get("main_factors") or [],
        "messages": latest.get("messages") or [],
    }
