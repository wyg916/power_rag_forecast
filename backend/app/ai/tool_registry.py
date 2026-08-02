from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import pandas as pd

from ..data_access import data_status, jsonable, model_status, price_column, query_dataframe, records, report_status, risk_probability_column
from ..source_contract import attach_source_meta, resolve_forecast_source
from ..stage1_services import (
    load_forecast,
    market_history,
    model_explain,
    prediction_latest,
    renewable_forecast,
    risk_level,
    weather_forecast,
)
from .knowledge_base import search_knowledge as search_knowledge_docs


def _forecast_frame(run_id: str = "latest") -> tuple[dict[str, Any], pd.DataFrame, str | None]:
    run, rows, meta = resolve_forecast_source(run_id)
    payload = attach_source_meta({"available": bool(rows), "run_id": run.get("run_id"), "records": rows}, meta)
    df = pd.DataFrame(rows)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    pcol = price_column(df) if not df.empty else None
    if pcol:
        df["__price"] = pd.to_numeric(df[pcol], errors="coerce")
    return payload, df, pcol


def _empty(name: str, message: str) -> dict[str, Any]:
    return {"tool": name, "available": False, "empty": True, "message": message, "unavailable_reason": "tool_no_data"}


def _hour_text(value: Any) -> str:
    dt = pd.to_datetime(value, errors="coerce")
    return dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else "-"


def _money(value: Any) -> str:
    try:
        return f"{float(value):.2f} USD/MWh"
    except Exception:
        return "-"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _prob_series(df: pd.DataFrame) -> pd.Series:
    prob_col = risk_probability_column(df)
    if prob_col and prob_col in df.columns:
        return pd.to_numeric(df[prob_col], errors="coerce").fillna(0)
    return pd.Series([0.0] * len(df), index=df.index)


def _risk_reasons(row: pd.Series, price: float, p75: float, prob: float, load_q75: float | None = None) -> list[str]:
    reasons: list[str] = []
    if price >= p75:
        reasons.append(f"预测电价 {_money(price)} 高于 P75 阈值 {_money(p75)}")
    if prob >= 0.5:
        reasons.append(f"尖峰风险概率 {prob:.2%} 偏高")
    if int(row.get("is_peak_hour") or 0) == 1:
        reasons.append("该时段属于系统标记的高峰小时")
    load = _num(row.get("forecast_load"), default=float("nan"))
    if load_q75 is not None and pd.notna(load) and load >= load_q75:
        reasons.append("预测负荷处于未来 24 小时较高水平")
    risk_level = str(row.get("risk_level") or "").lower()
    if risk_level in {"high", "高", "高风险"} and not reasons:
        reasons.append("系统风险标签为高风险")
    return reasons


def get_forecast_extremes(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    payload, df, pcol = _forecast_frame(run_id)
    if df.empty or not pcol:
        return _empty("get_forecast_extremes", "当前没有可用预测结果或预测电价字段。")
    prices = pd.to_numeric(df[pcol], errors="coerce")
    if not prices.notna().any():
        return _empty("get_forecast_extremes", "预测结果中没有可计算的电价值。")
    max_row = df.loc[prices.idxmax()]
    min_row = df.loc[prices.idxmin()]
    result = {
        "tool": "get_forecast_extremes",
        "run_id": payload.get("run_id") or run_id,
        "max_price_hour": _hour_text(max_row.get("datetime")),
        "max_price": _num(max_row.get(pcol)),
        "max_risk_level": max_row.get("risk_level"),
        "min_price_hour": _hour_text(min_row.get("datetime")),
        "min_price": _num(min_row.get(pcol)),
        "min_risk_level": min_row.get("risk_level"),
        "avg_price": _num(prices.mean()),
        "p25": _num(prices.quantile(0.25)),
        "p75": _num(prices.quantile(0.75)),
        "peak_valley_spread": _num(prices.max() - prices.min()),
        "rows": int(len(df)),
        "source": "正式预测结果",
    }
    return jsonable(result)


def get_high_risk_hours(run_id: str = "latest", limit: int = 6, **_: Any) -> dict[str, Any]:
    payload, df, pcol = _forecast_frame(run_id)
    if df.empty or not pcol:
        return _empty("get_high_risk_hours", "当前没有可用预测结果或预测电价字段。")
    prices = pd.to_numeric(df[pcol], errors="coerce")
    prob = _prob_series(df)
    p75 = _num(prices.quantile(0.75))
    load = pd.to_numeric(df.get("forecast_load", pd.Series([None] * len(df), index=df.index)), errors="coerce")
    load_q75 = _num(load.quantile(0.75), default=float("nan")) if load.notna().any() else None

    rows: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        price = _num(row.get(pcol), default=float("nan"))
        if pd.isna(price):
            continue
        risk_text = str(row.get("risk_level") or "").lower()
        probability = _num(prob.loc[idx]) if idx in prob.index else 0.0
        score = 0.0
        if risk_text in {"high", "高", "高风险"}:
            score += 3
        if risk_text in {"medium", "中", "中风险"}:
            score += 1
        if price >= p75:
            score += 1.2
        if probability >= 0.5:
            score += 2
        if int(row.get("is_peak_hour") or 0) == 1:
            score += 0.5
        reasons = _risk_reasons(row, price, p75, probability, load_q75)
        if score > 0 or reasons:
            rows.append(
                {
                    "hour": _hour_text(row.get("datetime")),
                    "predicted_price": price,
                    "risk_level": row.get("risk_level") or ("high" if score >= 3 else "medium"),
                    "spike_risk_prob": probability,
                    "forecast_load": row.get("forecast_load"),
                    "is_peak_hour": bool(row.get("is_peak_hour")),
                    "score": round(score, 2),
                    "reasons": reasons or ["价格或风险标签需要关注"],
                }
            )

    if not rows:
        top = df.loc[prices.nlargest(min(limit, len(df))).index]
        rows = [
            {
                "hour": _hour_text(row.get("datetime")),
                "predicted_price": _num(row.get(pcol)),
                "risk_level": row.get("risk_level") or "low",
                "spike_risk_prob": _num(row.get("spike_risk_prob")),
                "forecast_load": row.get("forecast_load"),
                "is_peak_hour": bool(row.get("is_peak_hour")),
                "score": 0,
                "reasons": ["暂无显著风险标签，按价格高位排序作为关注窗口"],
            }
            for _, row in top.iterrows()
        ]
    rows = sorted(rows, key=lambda item: (item.get("score", 0), item.get("predicted_price", 0)), reverse=True)[:limit]
    return jsonable({"tool": "get_high_risk_hours", "run_id": payload.get("run_id") or run_id, "items": rows, "thresholds": {"p75": p75}})


def get_hour_detail(run_id: str = "latest", hour: int | None = None, **_: Any) -> dict[str, Any]:
    payload, df, pcol = _forecast_frame(run_id)
    if df.empty or not pcol:
        return _empty("get_hour_detail", "当前没有可用预测结果或预测电价字段。")
    if hour is None:
        return _empty("get_hour_detail", "未识别到具体小时，请用“18点”或“18:00”这类说法提问。")
    matched = df[df["datetime"].dt.hour == int(hour)] if "datetime" in df.columns else pd.DataFrame()
    if matched.empty:
        return _empty("get_hour_detail", f"当前预测窗口内没有 {hour:02d}:00 的记录。")
    row = matched.iloc[0]
    prices = pd.to_numeric(df[pcol], errors="coerce")
    prob = _prob_series(df)
    load = pd.to_numeric(df.get("forecast_load", pd.Series([None] * len(df), index=df.index)), errors="coerce")
    load_q75 = _num(load.quantile(0.75), default=float("nan")) if load.notna().any() else None
    price = _num(row.get(pcol))
    probability = _num(prob.loc[row.name]) if row.name in prob.index else 0.0
    detail = {
        "tool": "get_hour_detail",
        "run_id": payload.get("run_id") or run_id,
        "requested_hour": hour,
        "hour": _hour_text(row.get("datetime")),
        "predicted_price": price,
        "avg_price": _num(prices.mean()),
        "p25": _num(prices.quantile(0.25)),
        "p75": _num(prices.quantile(0.75)),
        "risk_level": row.get("risk_level"),
        "spike_risk_prob": probability,
        "forecast_load": row.get("forecast_load"),
        "temperature": row.get("temperature"),
        "is_peak_hour": bool(row.get("is_peak_hour")),
        "reasons": _risk_reasons(row, price, _num(prices.quantile(0.75)), probability, load_q75),
    }
    return jsonable(detail)


def build_hour_risk_evidence(hour_detail: dict[str, Any], **_: Any) -> dict[str, Any]:
    if hour_detail.get("empty"):
        return _empty("build_hour_risk_evidence", hour_detail.get("message", "小时详情不足。"))
    reasons = hour_detail.get("reasons") or []
    recommendation = "建议交易员复核该小时的售电敞口、负荷预测和尖峰概率，必要时将该时段加入日报风险提示。"
    if not reasons:
        reasons = ["该小时未触发明显高价、尖峰或高负荷规则，风险主要按常规监控处理。"]
        recommendation = "建议按常规节奏跟踪，不宜把该小时单独视为高风险交易窗口。"
    return {
        "tool": "build_hour_risk_evidence",
        "hour": hour_detail.get("hour"),
        "reasons": reasons,
        "recommendation": recommendation,
    }


def get_trading_advice(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    extremes = get_forecast_extremes(run_id=run_id)
    risks = get_high_risk_hours(run_id=run_id, limit=5)
    if extremes.get("empty"):
        return extremes | {"tool": "get_trading_advice"}
    advice = {
        "tool": "get_trading_advice",
        "run_id": extremes.get("run_id"),
        "summary": f"未来 24 小时峰谷价差约 {_money(extremes.get('peak_valley_spread'))}，需要分高价、低价和风险窗口管理。",
        "high_price_window": {"hour": extremes.get("max_price_hour"), "price": extremes.get("max_price"), "action": "复核售电敞口和高价时段交易计划"},
        "low_price_window": {"hour": extremes.get("min_price_hour"), "price": extremes.get("min_price"), "action": "评估低成本采购、负荷转移或储能充电"},
        "risk_windows": risks.get("items", [])[:5] if not risks.get("empty") else [],
    }
    return jsonable(advice)


def get_storage_advice(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    payload, df, pcol = _forecast_frame(run_id)
    if df.empty or not pcol:
        return _empty("get_storage_advice", "当前没有可用预测结果或预测电价字段。")
    prices = pd.to_numeric(df[pcol], errors="coerce")
    spread = _num(prices.max() - prices.min())
    low_rows = df.loc[prices.nsmallest(min(3, len(df))).index]
    high_rows = df.loc[prices.nlargest(min(3, len(df))).index]
    return jsonable(
        {
            "tool": "get_storage_advice",
            "run_id": payload.get("run_id") or run_id,
            "peak_valley_spread": spread,
            "charge_windows": [{"hour": _hour_text(row.get("datetime")), "price": _num(row.get(pcol))} for _, row in low_rows.iterrows()],
            "discharge_windows": [{"hour": _hour_text(row.get("datetime")), "price": _num(row.get(pcol)), "risk_level": row.get("risk_level")} for _, row in high_rows.iterrows()],
            "min_spread_for_advice": 30,
        }
    )


def get_model_error_summary(days: int = 30, **_: Any) -> dict[str, Any]:
    status = model_status()
    errors = query_dataframe(
        """
        SELECT model_version, COUNT(*) AS sample_count, AVG(abs_error) AS mae, SQRT(AVG(POWER(abs_error, 2))) AS rmse, MAX(created_at) AS latest_record
        FROM prediction_tracking
        WHERE actual_price IS NOT NULL AND created_at >= CURRENT_TIMESTAMP - (:days * INTERVAL '1 day')
        GROUP BY model_version
        ORDER BY latest_record DESC
        LIMIT 5
        """,
        {"days": days},
    )
    return jsonable({"tool": "get_model_error_summary", "active_model": status.get("active") or {}, "error_rows": records(errors), "source": status.get("source")})


def get_report_summary(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    report = report_status(run_id)
    summary = report.get("summary") or {}
    return jsonable(
        {
            "tool": "get_report_summary",
            "report_id": report.get("report_id"),
            "available": report.get("available"),
            "generated_at": report.get("generated_at"),
            "fallback_used": report.get("fallback_used"),
            "summary": summary,
        }
    )


def get_data_status(**_: Any) -> dict[str, Any]:
    payload = data_status()
    return jsonable({"tool": "get_data_status", "sources": payload.get("sources", []), "checked_at": datetime.now().isoformat(sep=" ", timespec="seconds")})


def compare_with_yesterday(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    extremes = get_forecast_extremes(run_id=run_id)
    if extremes.get("empty"):
        return extremes | {"tool": "compare_with_yesterday"}
    return jsonable(
        {
            "tool": "compare_with_yesterday",
            "current": extremes,
            "message": "当前 Web 侧未加载可比历史预测窗口，不能严谨计算昨日对比；可先基于当前最高价、最低价和峰谷价差做当日内判断。",
        }
    )


def get_prediction_overview(market: str | None = None, date: str | None = None, **_: Any) -> dict[str, Any]:
    overview = prediction_latest(market=market, date=date)
    return jsonable({"tool": "get_prediction_overview", "overview": overview, **{k: overview.get(k) for k in ["available", "risk_level", "focus_periods", "main_factors"]}})


def get_market_history(market: str | None = None, start: str | None = None, end: str | None = None, **_: Any) -> dict[str, Any]:
    payload = market_history(market=market, start=start, end=end)
    return jsonable({"tool": "get_market_history", **payload})


def get_weather_forecast(city: str | None = None, date: str | None = None, **_: Any) -> dict[str, Any]:
    payload = weather_forecast(city=city, date=date)
    return jsonable({"tool": "get_weather_forecast", **payload})


def get_load_forecast(market: str | None = None, date: str | None = None, **_: Any) -> dict[str, Any]:
    payload = load_forecast(market=market, date=date)
    return jsonable({"tool": "get_load_forecast", **payload})


def get_renewable_forecast(market: str | None = None, date: str | None = None, **_: Any) -> dict[str, Any]:
    payload = renewable_forecast(market=market, date=date)
    return jsonable({"tool": "get_renewable_forecast", **payload})


def get_model_explain(market: str | None = None, date: str | None = None, **_: Any) -> dict[str, Any]:
    payload = model_explain(market=market, date=date)
    return jsonable({"tool": "get_model_explain", **payload})


def get_risk_level(market: str | None = None, date: str | None = None, **_: Any) -> dict[str, Any]:
    payload = risk_level(market=market, date=date)
    return jsonable({"tool": "get_risk_level", **payload})


def search_knowledge(question: str = "", **_: Any) -> dict[str, Any]:
    items = search_knowledge_docs(question)
    return {"tool": "search_knowledge", "items": items, "available": bool(items)}


ToolFunc = Callable[..., dict[str, Any]]

TOOLS: dict[str, ToolFunc] = {
    "get_prediction_overview": get_prediction_overview,
    "get_market_history": get_market_history,
    "get_weather_forecast": get_weather_forecast,
    "get_load_forecast": get_load_forecast,
    "get_renewable_forecast": get_renewable_forecast,
    "get_model_explain": get_model_explain,
    "get_risk_level": get_risk_level,
    "search_knowledge": search_knowledge,
    "get_forecast_extremes": get_forecast_extremes,
    "get_high_risk_hours": get_high_risk_hours,
    "get_hour_detail": get_hour_detail,
    "build_hour_risk_evidence": build_hour_risk_evidence,
    "get_trading_advice": get_trading_advice,
    "get_storage_advice": get_storage_advice,
    "get_model_error_summary": get_model_error_summary,
    "get_report_summary": get_report_summary,
    "get_data_status": get_data_status,
    "compare_with_yesterday": compare_with_yesterday,
}

INTENT_TOOLS: dict[str, list[str]] = {
    "forecast_overview": ["get_prediction_overview", "get_risk_level"],
    "forecast_extreme": ["get_forecast_extremes"],
    "risk_hours": ["get_high_risk_hours"],
    "hour_explain": ["get_hour_detail", "build_hour_risk_evidence"],
    "factor_analysis": ["get_prediction_overview", "get_load_forecast", "get_weather_forecast", "get_renewable_forecast", "get_model_explain", "search_knowledge"],
    "weather_analysis": ["get_weather_forecast", "search_knowledge"],
    "load_analysis": ["get_load_forecast", "search_knowledge"],
    "renewable_analysis": ["get_renewable_forecast", "search_knowledge"],
    "strategy_advice": ["get_trading_advice"],
    "storage_advice": ["get_storage_advice"],
    "compare_history": ["compare_with_yesterday"],
    "model_status": ["get_model_error_summary", "get_model_explain"],
    "report_summary": ["get_report_summary"],
    "data_status": ["get_data_status"],
    "general_analysis": ["get_forecast_extremes", "get_high_risk_hours", "get_trading_advice"],
}


def call_tools(intent: str, entities: dict[str, object], run_id: str = "latest", question: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    for name in INTENT_TOOLS.get(intent, INTENT_TOOLS["general_analysis"]):
        args: dict[str, Any] = {
            "run_id": run_id,
            "market": entities.get("market"),
            "date": entities.get("date"),
            "question": question,
        }
        if name == "get_hour_detail":
            args["hour"] = entities.get("hour")
        try:
            if name == "build_hour_risk_evidence":
                args = {"hour_detail": results[-1] if results else {}}
            result = TOOLS[name](**args)
            success = not bool(result.get("empty"))
            results.append(result)
            calls.append({"tool_name": name, "input": args, "success": success, "output": result})
        except Exception as exc:
            error = {"tool": name, "empty": True, "message": str(exc)}
            results.append(error)
            calls.append({"tool_name": name, "input": args, "success": False, "error_message": str(exc), "output": error})
    return results, calls
