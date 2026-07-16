from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any

from ..data_access import data_status, jsonable, load_latest_forecast, model_status, report_status
from ..platform_services import generate_strategy_advice, list_report_reviews
from ..repositories.task_repository import list_recent_tasks, task_runtime_summary


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _time_text(value: Any, fmt: str = "%H:%M") -> str:
    text = str(value or "")
    if not text:
        return "--"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime(fmt)
    except ValueError:
        return text[11:16] if len(text) >= 16 else text[:16]


def _price_of(row: dict[str, Any]) -> float | None:
    for key in (
        "corrected_predicted_price",
        "predicted_price",
        "forecast_price",
        "da_price_pred",
        "预测电价",
        "预测日前电价",
    ):
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


def _load_of(row: dict[str, Any]) -> float | None:
    for key in ("forecast_load", "predicted_load", "load", "预测负荷", "负荷"):
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


def _risk_probability(row: dict[str, Any]) -> float | None:
    for key in ("spike_risk_prob", "risk_probability", "risk_prob", "尖峰风险概率"):
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


def _risk_level(row: dict[str, Any], probability: float | None = None) -> str:
    raw = str(row.get("risk_level") or "").strip().lower()
    if raw in {"high", "danger", "高", "高风险"}:
        return "high"
    if raw in {"medium", "warning", "中", "中风险"}:
        return "medium"
    if raw in {"low", "success", "低", "低风险"}:
        return "low"
    probability = probability if probability is not None else _risk_probability(row)
    if probability is None:
        return "low"
    if probability >= 0.5:
        return "high"
    if probability >= 0.2:
        return "medium"
    return "low"


def _confidence_bounds(row: dict[str, Any], price: float, spread: float) -> tuple[float, float, str]:
    upper = _num(row.get("upper")) or _num(row.get("p90_price")) or _num(row.get("prediction_upper"))
    lower = _num(row.get("lower")) or _num(row.get("p10_price")) or _num(row.get("prediction_lower"))
    if upper is not None and lower is not None:
        return lower, upper, "model_output"
    margin = max(abs(price) * 0.08, spread * 0.04, 0.01)
    return price - margin, price + margin, "derived_from_forecast_price"


def forecast_24h_payload() -> dict[str, Any]:
    forecast = load_latest_forecast()
    raw_records = list(forecast.get("records") or [])[:24]
    prices = [value for value in (_price_of(row) for row in raw_records) if value is not None]
    spread = (max(prices) - min(prices)) if prices else 0
    confidence_sources: set[str] = set()
    series: list[dict[str, Any]] = []
    for index, row in enumerate(raw_records):
        price = _price_of(row)
        if price is None:
            continue
        lower, upper, confidence_source = _confidence_bounds(row, price, spread)
        confidence_sources.add(confidence_source)
        probability = _risk_probability(row)
        series.append(
            {
                "index": index,
                "datetime": row.get("datetime"),
                "time": _time_text(row.get("datetime")),
                "price": price,
                "load": _load_of(row),
                "risk_probability": probability,
                "risk_level": _risk_level(row, probability),
                "lower": lower,
                "upper": upper,
                "source_row": row.get("source_row"),
            }
        )

    sorted_by_price = sorted(series, key=lambda item: item["price"])
    low_price = sorted_by_price[:3]
    high_price = sorted_by_price[-3:][::-1]
    high_risk = [
        item
        for item in series
        if item["risk_level"] == "high" or _num(item.get("risk_probability")) and float(item["risk_probability"]) >= 0.5
    ]
    prices = [float(item["price"]) for item in series]
    loads = [float(item["load"]) for item in series if item.get("load") is not None]
    summary = dict(forecast.get("summary") or {})
    summary.update(
        {
            "record_count": len(series),
            "max_price": max(prices) if prices else None,
            "min_price": min(prices) if prices else None,
            "avg_price": mean(prices) if prices else None,
            "peak_valley_spread": (max(prices) - min(prices)) if prices else None,
            "max_hour": max(series, key=lambda item: item["price"]).get("datetime") if series else None,
            "min_hour": min(series, key=lambda item: item["price"]).get("datetime") if series else None,
            "high_risk_hours": len(high_risk),
            "avg_load": mean(loads) if loads else None,
        }
    )
    return jsonable(
        {
            "available": bool(series),
            "run_id": forecast.get("run_id"),
            "generated_at": forecast.get("generated_at"),
            "data_source": forecast.get("source_type") or ("api_forecast_file" if forecast.get("available") else "api_forecast_empty"),
            "source": forecast.get("source"),
            "unit": "元/kWh",
            "series": series,
            "summary": summary,
            "windows": {
                "low_price": low_price,
                "high_price": high_price,
                "high_risk": high_risk[:6],
            },
            "quality": {
                "record_count": len(series),
                "missing_price_count": max(len(raw_records) - len(series), 0),
                "missing_load_count": len([item for item in series if item.get("load") is None]),
                "derived_fields": ["confidence_interval"] if "derived_from_forecast_price" in confidence_sources else [],
                "confidence_source": ",".join(sorted(confidence_sources)) if confidence_sources else "",
            },
        }
    )


def risk_summary_payload() -> dict[str, Any]:
    forecast = forecast_24h_payload()
    series = forecast.get("series") or []
    probabilities = [_num(item.get("risk_probability")) for item in series]
    probabilities = [value for value in probabilities if value is not None]
    prices = [float(item.get("price")) for item in series if item.get("price") is not None]
    high_risk = [item for item in series if item.get("risk_level") == "high"]
    medium_risk = [item for item in series if item.get("risk_level") == "medium"]
    spread = max(prices) - min(prices) if prices else 0
    avg_price = mean(prices) if prices else 0
    spread_score = min(40, (spread / avg_price * 40) if avg_price else 0)
    probability_score = max(probabilities) * 100 if probabilities else 0
    density_score = min(30, len(high_risk) / max(len(series), 1) * 100)
    risk_index = round(min(100, max(probability_score, spread_score + density_score)), 1)
    if risk_index >= 70 or len(high_risk) >= 3:
        level = "high"
    elif risk_index >= 40 or medium_risk:
        level = "medium"
    else:
        level = "low"
    alerts: list[dict[str, Any]] = []
    if high_risk:
        first = high_risk[0]
        alerts.append(
            {
                "level": "high",
                "title": "高风险时段",
                "description": f"{first.get('time')} 起存在高风险预测窗口，建议人工复核负荷、价格与交易计划。",
                "target_time": first.get("datetime"),
            }
        )
    if prices and spread:
        alerts.append(
            {
                "level": "medium" if level != "high" else "high",
                "title": "峰谷价差",
                "description": f"未来 24 小时峰谷价差 {spread:.3f} 元/kWh，需关注价格弹性与策略窗口。",
                "target_time": None,
            }
        )
    return jsonable(
        {
            "available": bool(series),
            "data_source": "derived_from_api_forecast_24h",
            "risk_index": risk_index,
            "risk_level": level,
            "high_risk_count": len(high_risk),
            "medium_risk_count": len(medium_risk),
            "high_risk_windows": high_risk[:6],
            "alerts": alerts,
            "summary": forecast.get("summary") or {},
        }
    )


def strategy_today_payload() -> dict[str, Any]:
    strategy = generate_strategy_advice(persist=False)
    forecast = forecast_24h_payload()
    items = list(strategy.get("items") or [])
    must_watch = [item for item in items if item.get("category") == "交易必看" or item.get("risk_level") == "high"]
    storage = [item for item in items if str(item.get("scenario") or "") == "储能"]
    prices = [float(item.get("price")) for item in forecast.get("series") or [] if item.get("price") is not None]
    estimated_revenue = None
    revenue_note = "待接入真实执行收益回填"
    if prices:
        estimated_revenue = round(max(prices) - min(prices), 4)
        revenue_note = "由真实预测电价峰谷价差派生，仅表示套利价差，不等同实际收益"
    return jsonable(
        {
            "available": bool(items),
            "run_id": strategy.get("run_id"),
            "data_source": "api_strategy_latest",
            "items": items,
            "must_watch": must_watch[:6],
            "storage_items": storage[:6],
            "summary": {
                "strategy_count": len(items),
                "must_watch_count": len(must_watch),
                "storage_count": len(storage),
                "estimated_revenue": estimated_revenue,
                "estimated_revenue_unit": "元/kWh价差",
                "estimated_revenue_note": revenue_note,
                "thresholds": strategy.get("thresholds") or {},
            },
            "message": strategy.get("message") or "",
        }
    )


def task_recent_payload(limit: int = 8) -> dict[str, Any]:
    runtime = task_runtime_summary()
    rows = list_recent_tasks(limit=max(limit, 30))
    if not rows and not runtime.get("available"):
        rows = []
    reminders = [
        row
        for row in rows
        if str(row.get("status") or "").lower() in {"failed", "timeout", "pending", "queued", "retrying", "running"}
    ]
    return jsonable(
        {
            "available": bool(rows) or bool(runtime.get("available")),
            "data_source": "postgresql.task_runs",
            "items": rows[:limit],
            "reminders": reminders[:limit],
            "health": runtime,
        }
    )


def _data_health_score() -> dict[str, Any]:
    status = data_status()
    sources = status.get("sources") or []
    if not sources:
        return {"score": None, "exception_count": 0, "source_count": 0, "sources": [], "data_source": "api_data_status_empty"}
    exception_count = 0
    missing_total = 0
    row_total = 0
    for source in sources:
        status_text = str(source.get("status") or "").lower()
        if status_text not in {"正常", "success", "ok"}:
            exception_count += 1
        missing_total += int(source.get("missing_values") or 0)
        row_total += int(source.get("rows") or 0)
    missing_penalty = min(30, (missing_total / row_total * 100) if row_total else 0)
    exception_penalty = (exception_count / len(sources)) * 40
    score = round(max(0, 100 - missing_penalty - exception_penalty), 1)
    return {
        "score": score,
        "exception_count": exception_count,
        "source_count": len(sources),
        "sources": sources,
        "data_source": "derived_from_api_data_status",
    }


def _forecast_confidence() -> dict[str, Any]:
    model = model_status()
    active = model.get("active") or {}
    mae = _num(active.get("test_mae") or active.get("mae"))
    rmse = _num(active.get("test_rmse") or active.get("rmse"))
    forecast = forecast_24h_payload()
    avg_price = _num((forecast.get("summary") or {}).get("avg_price"))
    confidence = None
    if mae is not None and avg_price:
        confidence = round(max(0, min(100, 100 - abs(mae / avg_price) * 100)), 1)
    return {
        "confidence": confidence,
        "mae": mae,
        "rmse": rmse,
        "model": active,
        "data_source": active.get("data_source") or model.get("source") or "model_registry",
    }


def _report_pending_count() -> dict[str, Any]:
    report = report_status()
    if not report.get("available"):
        return {"count": 0, "report": report, "data_source": "api_reports_latest"}
    report_id = str(report.get("report_id") or "latest")
    reviews = list_report_reviews(report_id)
    finished = any(str(item.get("status") or "").lower() in {"approved", "published"} for item in reviews)
    return {"count": 0 if finished else 1, "report": report, "reviews": reviews, "data_source": "report_status+report_reviews"}


def dashboard_kpi_payload() -> dict[str, Any]:
    forecast = forecast_24h_payload()
    risk = risk_summary_payload()
    strategy = strategy_today_payload()
    tasks = task_recent_payload(limit=8)
    data_health = _data_health_score()
    confidence = _forecast_confidence()
    report_pending = _report_pending_count()
    series = forecast.get("series") or []
    risk_sparkline = [round(float(item.get("risk_probability") or 0) * 100, 2) for item in series]
    price_sparkline = [round(float(item.get("price") or 0), 4) for item in series]
    task_health = tasks.get("health") or {}
    task_health_available = task_health.get("available") is not False and not task_health.get("error")
    task_problem_count = int(task_health.get("failed_task_count") or 0) + int(task_health.get("timeout_task_count") or 0)
    items = [
        {
            "key": "supply_demand_risk",
            "title": "高风险窗口数",
            "value": risk.get("high_risk_count"),
            "unit": "个",
            "status": risk.get("risk_level"),
            "trend_label": "由 forecast_results 风险概率统计，非 mock",
            "sparkline": risk_sparkline or price_sparkline,
            "data_source": risk.get("data_source"),
        },
        {
            "key": "forecast_confidence",
            "title": "预测可信度",
            "value": confidence.get("confidence"),
            "unit": "%",
            "status": "success" if confidence.get("confidence") is not None and confidence["confidence"] >= 85 else "warning",
            "trend_label": "来自模型评估" if confidence.get("confidence") is not None else "待接入真实误差回填",
            "sparkline": price_sparkline,
            "data_source": confidence.get("data_source"),
        },
        {
            "key": "strategy_revenue",
            "title": "策略预计收益",
            "value": (strategy.get("summary") or {}).get("estimated_revenue"),
            "unit": (strategy.get("summary") or {}).get("estimated_revenue_unit"),
            "status": "success" if (strategy.get("summary") or {}).get("estimated_revenue") is not None else "pending",
            "trend_label": (strategy.get("summary") or {}).get("estimated_revenue_note"),
            "sparkline": price_sparkline,
            "data_source": "derived_from_api_strategy_today",
        },
        {
            "key": "report_pending",
            "title": "报告待审",
            "value": report_pending.get("count"),
            "unit": "份",
            "status": "warning" if int(report_pending.get("count") or 0) else "success",
            "trend_label": "来自报告状态与审核记录",
            "sparkline": [],
            "data_source": report_pending.get("data_source"),
        },
        {
            "key": "task_reminder",
            "title": "任务提醒",
            "value": len(tasks.get("reminders") or []),
            "unit": "项",
            "status": "warning" if not task_health_available else ("danger" if task_problem_count else ("warning" if tasks.get("reminders") else "success")),
            "trend_label": (
                f"任务健康统计待接入：{str(task_health.get('error'))[:80]}"
                if not task_health_available
                else f"失败/超时 {task_problem_count} 项"
            ),
            "sparkline": [],
            "data_source": tasks.get("data_source"),
        },
        {
            "key": "data_health",
            "title": "数据健康",
            "value": data_health.get("score"),
            "unit": "%",
            "status": "success" if data_health.get("score") is not None and data_health["score"] >= 90 else "warning",
            "trend_label": f"异常源 {data_health.get('exception_count', 0)} / {data_health.get('source_count', 0)}",
            "sparkline": [],
            "data_source": data_health.get("data_source"),
        },
    ]
    return jsonable(
        {
            "available": any(item.get("value") is not None for item in items),
            "data_source": "api_dashboard_kpi",
            "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "items": items,
            "context": {
                "forecast": forecast.get("summary") or {},
                "forecast_confidence": confidence,
                "risk": risk,
                "strategy": strategy.get("summary") or {},
                "tasks": task_health,
                "data_health": data_health,
            },
        }
    )


def dashboard_model_status_payload() -> dict[str, Any]:
    confidence = _forecast_confidence()
    model = confidence.get("model") or {}
    version = model.get("model_version") or model.get("version")
    is_demo = bool(model.get("is_demo") or str(confidence.get("data_source") or "").lower() in {"seed_demo", "dashboard_seed"})
    return jsonable(
        {
            "available": bool(model),
            "data_source": "seed_demo" if is_demo else confidence.get("data_source"),
            "is_demo": is_demo,
            "status": model.get("status") or ("Active" if model.get("is_active") else "unknown"),
            "version": version,
            "confidence": confidence.get("confidence"),
            "mae": confidence.get("mae"),
            "rmse": confidence.get("rmse"),
            "activated_at": model.get("activated_at") or model.get("updated_at") or model.get("created_at"),
            "model": model,
        }
    )


def dashboard_data_health_payload() -> dict[str, Any]:
    payload = _data_health_score()
    payload["available"] = payload.get("score") is not None or bool(payload.get("sources"))
    payload["covered_sources"] = payload.get("source_count", 0)
    payload["abnormal_sources"] = payload.get("exception_count", 0)
    return jsonable(payload)


def dashboard_task_reminders_payload(limit: int = 8) -> dict[str, Any]:
    tasks = task_recent_payload(limit=limit)
    health = tasks.get("health") or {}
    failed_or_timeout = int(health.get("failed_task_count") or 0) + int(health.get("timeout_task_count") or 0)
    return jsonable(
        {
            "available": tasks.get("available"),
            "data_source": tasks.get("data_source"),
            "items": tasks.get("items") or [],
            "reminders": tasks.get("reminders") or [],
            "summary": {
                "running": int(health.get("running_task_count") or 0),
                "queued": int(health.get("pending_task_count") or 0),
                "failed_or_timeout": failed_or_timeout,
            },
            "health": health,
        }
    )


def dashboard_supply_demand_risk_payload() -> dict[str, Any]:
    forecast = forecast_24h_payload()
    risk = risk_summary_payload()
    risk_windows = risk.get("high_risk_windows") or (forecast.get("windows") or {}).get("high_risk") or []
    return jsonable(
        {
            "available": bool(forecast.get("available") or risk.get("available")),
            "data_source": "postgresql_dashboard_forecast_risk",
            "forecast": forecast,
            "risk": risk,
            "series": forecast.get("series") or [],
            "risk_windows": risk_windows,
            "windows": forecast.get("windows") or {},
            "unit": forecast.get("unit") or "元/kWh",
            "summary": {
                **(forecast.get("summary") or {}),
                "risk_index": risk.get("risk_index"),
                "risk_level": risk.get("risk_level"),
                "high_risk_count": risk.get("high_risk_count"),
                "medium_risk_count": risk.get("medium_risk_count"),
            },
        }
    )


def dashboard_forecast_metrics_payload() -> dict[str, Any]:
    forecast = forecast_24h_payload()
    summary = forecast.get("summary") or {}
    metrics = [
        {"key": "max_price", "title": "最高价", "value": summary.get("max_price"), "unit": "元/kWh", "at": summary.get("max_hour")},
        {"key": "min_price", "title": "最低价", "value": summary.get("min_price"), "unit": "元/kWh", "at": summary.get("min_hour")},
        {"key": "avg_price", "title": "均价", "value": summary.get("avg_price"), "unit": "元/kWh", "sample_count": summary.get("record_count")},
        {
            "key": "peak_valley_spread",
            "title": "峰谷价差",
            "value": summary.get("peak_valley_spread"),
            "unit": "元/kWh",
            "high_risk_hours": summary.get("high_risk_hours"),
        },
    ]
    return jsonable(
        {
            "available": bool(forecast.get("available")),
            "data_source": forecast.get("data_source"),
            "summary": summary,
            "metrics": metrics,
        }
    )


def dashboard_ai_suggestions_payload() -> dict[str, Any]:
    strategy = strategy_today_payload()
    risk = risk_summary_payload()
    items = [
        *(strategy.get("must_watch") or []),
        *(strategy.get("items") or []),
        *(risk.get("alerts") or []),
    ]
    return jsonable(
        {
            "available": bool(items),
            "data_source": strategy.get("data_source") or risk.get("data_source"),
            "items": items[:8],
            "strategy": strategy,
            "risk": risk,
        }
    )


def dashboard_strategy_execution_payload() -> dict[str, Any]:
    strategy = strategy_today_payload()
    summary = strategy.get("summary") or {}
    return jsonable(
        {
            "available": strategy.get("available"),
            "data_source": strategy.get("data_source"),
            "summary": summary,
            "generated_strategies": int(summary.get("strategy_count") or 0),
            "high_price_risk_windows": int(summary.get("must_watch_count") or 0),
            "low_price_storage_windows": int(summary.get("storage_count") or 0),
            "expected_spread": summary.get("estimated_revenue"),
            "items": strategy.get("items") or [],
            "must_watch": strategy.get("must_watch") or [],
            "storage_items": strategy.get("storage_items") or [],
        }
    )


def dashboard_context_payload() -> dict[str, Any]:
    kpi = dashboard_kpi_payload()
    context = kpi.get("context") or {}
    forecast = context.get("forecast") or {}
    model_status_payload = dashboard_model_status_payload()
    return jsonable(
        {
            "available": bool(context),
            "data_source": kpi.get("data_source"),
            "generated_at": kpi.get("generated_at"),
            "project": {"name": "华东虚拟电厂示范项目"},
            "region": "浙江省",
            "data_time": forecast.get("forecast_end") or forecast.get("max_hour") or kpi.get("generated_at"),
            "model": {
                "version": model_status_payload.get("version") or "v3.2.1",
                "status": model_status_payload.get("status"),
            },
            "user": {"username": "admin"},
            "notification_count": 12,
            **context,
        }
    )


def dashboard_overview_payload() -> dict[str, Any]:
    partial_errors: list[str] = []

    def collect(key: str, loader: Any) -> dict[str, Any]:
        try:
            value = loader()
            return value if isinstance(value, dict) else {"available": bool(value), "value": value}
        except Exception as exc:  # pragma: no cover - defensive aggregation boundary
            partial_errors.append(f"{key}: {exc}")
            return {"available": False, "error": str(exc), "data_source": f"{key}_error"}

    forecast = collect("forecast", forecast_24h_payload)
    risk = collect("risk", risk_summary_payload)
    strategy = collect("strategy", strategy_today_payload)
    tasks = collect("tasks", lambda: task_recent_payload(limit=8))
    kpi = collect("kpi", dashboard_kpi_payload)
    risk_chart = collect("risk_chart", dashboard_supply_demand_risk_payload)
    forecast_metrics_payload = collect("forecast_metrics", dashboard_forecast_metrics_payload)
    ai_suggestions_payload = collect("ai_suggestions", dashboard_ai_suggestions_payload)
    strategy_summary = collect("strategy_summary", dashboard_strategy_execution_payload)
    model_status_payload = collect("model_status", dashboard_model_status_payload)
    data_health_payload = collect("data_health", dashboard_data_health_payload)
    task_reminders = collect("task_reminders", lambda: dashboard_task_reminders_payload(limit=8))
    context = collect("context", dashboard_context_payload)
    generated_at = datetime.now().isoformat(sep=" ", timespec="seconds")
    sources = [
        kpi.get("data_source"),
        risk.get("data_source"),
        strategy.get("data_source"),
        forecast.get("data_source"),
        tasks.get("data_source"),
        model_status_payload.get("data_source"),
        data_health_payload.get("data_source"),
        task_reminders.get("data_source"),
    ]
    generated_from_seed = bool(model_status_payload.get("is_demo"))
    return jsonable(
        {
            "available": any(payload.get("available") for payload in (kpi, risk, strategy, forecast, tasks)),
            "data_source": "postgresql_dashboard_overview",
            "generated_at": generated_at,
            "loadedAt": generated_at,
            "partialErrors": partial_errors,
            "partial_errors": partial_errors,
            "sources": [source for source in sources if source],
            "context": context,
            "kpis": kpi.get("items") or [],
            "risk_chart": {
                "available": risk_chart.get("available"),
                "series": risk_chart.get("series") or [],
                "risk_windows": risk_chart.get("risk_windows") or [],
                "windows": risk_chart.get("windows") or {},
                "summary": risk_chart.get("summary") or {},
                "unit": risk_chart.get("unit") or "元/kWh",
                "data_source": risk_chart.get("data_source"),
            },
            "forecast_metrics": forecast_metrics_payload.get("metrics") or [],
            "ai_suggestions": ai_suggestions_payload.get("items") or [],
            "strategy_summary": strategy_summary,
            "model_status": model_status_payload,
            "data_health": data_health_payload,
            "task_reminders": task_reminders,
            "data_source": {
                "primary": "postgresql",
                "is_demo": generated_from_seed,
                "generated_from_seed": generated_from_seed,
                "detail": [source for source in sources if source],
            },
            "kpi": kpi,
            "risk": risk,
            "strategy": strategy,
            "forecast": forecast,
            "tasks": tasks,
        }
    )
