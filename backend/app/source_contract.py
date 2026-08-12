from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from .repositories.forecast_repository import (
    get_forecast_run,
    latest_successful_run,
    load_forecast_results,
)


PROJECT_TIMEZONE = ZoneInfo("Asia/Shanghai")


class SourceType(str, Enum):
    REAL = "real"
    HISTORICAL = "historical"
    SIMULATED = "simulated"
    DEMO = "demo"
    SEED = "seed"
    FALLBACK = "fallback"
    DERIVED = "derived"
    AI_INFERRED = "ai_inferred"
    UNAVAILABLE = "unavailable"


SUPPORTED_DOMAINS = {
    "electricity_day_ahead_price",
    "electricity_real_time_price",
    "load_forecast",
    "weather",
    "report",
    "strategy",
    "model_registry",
    "data_quality",
    "task",
    "system",
}


class SourceMeta(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    source_type: SourceType
    data_origin: str
    source_name: str
    domain: str
    run_id: str | None = None
    generated_at: str | None = None
    updated_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    model_version: str | None = None
    feature_version: str | None = None
    schema_hash: str | None = None
    data_version: str | None = None
    freshness_status: str
    is_stale: bool = False
    stale_reason: str | None = None
    staleness_reason: str | None = None
    expected_refresh_at: str | None = None
    simulation: bool = False
    degraded: bool = False
    availability: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    unavailable_reason: str | None = None
    fallback_reason: str | None = None


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PROJECT_TIMEZONE)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _datetime(value: Any) -> datetime | None:
    text = _iso(value)
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def _validate_domain(domain: str) -> str:
    normalized = str(domain or "").strip()
    if normalized not in SUPPORTED_DOMAINS:
        raise ValueError(f"unsupported_domain:{normalized or 'empty'}")
    return normalized


def source_meta(
    source_type: SourceType | str,
    domain: str,
    *,
    run_id: str | None = None,
    source_name: str | None = None,
    generated_at: Any = None,
    updated_at: Any = None,
    valid_from: Any = None,
    valid_to: Any = None,
    model_version: str | None = None,
    feature_version: str | None = None,
    schema_hash: str | None = None,
    data_version: str | None = None,
    is_stale: bool = False,
    stale_reason: str | None = None,
    expected_refresh_at: Any = None,
    evidence: list[dict[str, Any]] | None = None,
    unavailable_reason: str | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    value = SourceType(source_type)
    stale = bool(is_stale or value is SourceType.HISTORICAL)
    resolved_stale_reason = stale_reason or ("historical_record" if value is SourceType.HISTORICAL else None)
    if value is SourceType.REAL:
        data_origin = "real_historical" if stale else "real_current"
    elif value is SourceType.HISTORICAL:
        data_origin = "real_historical"
    elif value is SourceType.SIMULATED:
        data_origin = "simulation"
    elif value in {SourceType.DEMO, SourceType.SEED}:
        data_origin = "seed"
    elif value is SourceType.FALLBACK:
        data_origin = "degraded"
    elif value is SourceType.AI_INFERRED:
        data_origin = "ai_inferred"
    elif value is SourceType.UNAVAILABLE:
        data_origin = "unavailable"
    else:
        data_origin = "derived"
    degraded = value is SourceType.FALLBACK
    availability = "unavailable" if value is SourceType.UNAVAILABLE else "degraded" if degraded else "available"
    freshness_status = (
        "unavailable" if value is SourceType.UNAVAILABLE
        else "degraded" if degraded
        else "historical" if value is SourceType.HISTORICAL
        else "stale" if stale
        else "current"
    )
    return SourceMeta(
        source_type=value,
        data_origin=data_origin,
        source_name=str(source_name or f"{domain}_service"),
        domain=_validate_domain(domain),
        run_id=run_id,
        generated_at=_iso(generated_at),
        updated_at=_iso(updated_at if updated_at is not None else generated_at),
        valid_from=_iso(valid_from),
        valid_to=_iso(valid_to),
        model_version=model_version,
        feature_version=feature_version,
        schema_hash=schema_hash,
        data_version=data_version or schema_hash,
        freshness_status=freshness_status,
        is_stale=stale,
        stale_reason=resolved_stale_reason,
        staleness_reason=resolved_stale_reason,
        expected_refresh_at=_iso(expected_refresh_at),
        simulation=value is SourceType.SIMULATED,
        degraded=degraded,
        availability=availability,
        evidence=evidence or [],
        unavailable_reason=unavailable_reason,
        fallback_reason=fallback_reason,
    ).model_dump()


def attach_source_meta(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    normalized_meta = dict(meta)
    source_type = str(normalized_meta.get("source_type") or SourceType.UNAVAILABLE.value)
    stale = bool(normalized_meta.get("is_stale") or source_type == SourceType.HISTORICAL.value)
    normalized_meta["is_stale"] = stale
    origin_map = {
        SourceType.REAL.value: "real_historical" if stale else "real_current",
        SourceType.HISTORICAL.value: "real_historical",
        SourceType.SIMULATED.value: "simulation",
        SourceType.DEMO.value: "seed",
        SourceType.SEED.value: "seed",
        SourceType.FALLBACK.value: "degraded",
        SourceType.DERIVED.value: "derived",
        SourceType.AI_INFERRED.value: "ai_inferred",
        SourceType.UNAVAILABLE.value: "unavailable",
    }
    normalized_meta["data_origin"] = origin_map.get(source_type, "unavailable")
    normalized_meta["simulation"] = source_type == SourceType.SIMULATED.value
    normalized_meta["degraded"] = source_type == SourceType.FALLBACK.value
    normalized_meta["availability"] = (
        "unavailable" if source_type == SourceType.UNAVAILABLE.value
        else "degraded" if normalized_meta["degraded"]
        else "available"
    )
    normalized_meta["freshness_status"] = (
        "unavailable" if source_type == SourceType.UNAVAILABLE.value
        else "degraded" if normalized_meta["degraded"]
        else "historical" if source_type == SourceType.HISTORICAL.value
        else "stale" if stale
        else "current"
    )
    normalized_meta["stale_reason"] = normalized_meta.get("stale_reason") or ("historical_record" if source_type == SourceType.HISTORICAL.value else None)
    normalized_meta["staleness_reason"] = normalized_meta.get("staleness_reason") or normalized_meta.get("stale_reason")

    items = payload.get("items") or []
    item = items[0] if items and isinstance(items[0], dict) else payload
    metadata = item.get("metadata") if isinstance(item, dict) else {}
    summary = item.get("summary") if isinstance(item, dict) else {}
    source = summary.get("source") if isinstance(summary, dict) else {}
    contexts = [payload, item, metadata or {}, source or {}]

    def first_value(*keys: str) -> Any:
        for context in contexts:
            if not isinstance(context, dict):
                continue
            for key in keys:
                value = context.get(key)
                if value is not None and value != "":
                    return value
        return None

    domain = str(normalized_meta.get("domain") or "system")
    normalized_meta["source_name"] = normalized_meta.get("source_name") or f"{domain}_service"
    normalized_meta["updated_at"] = normalized_meta.get("updated_at") or _iso(first_value("updated_at", "generated_at"))
    normalized_meta["valid_from"] = normalized_meta.get("valid_from") or _iso(first_value("valid_from", "forecast_start_at", "applicable_start_at"))
    normalized_meta["valid_to"] = normalized_meta.get("valid_to") or _iso(first_value("valid_to", "forecast_end_at", "applicable_end_at"))
    normalized_meta["data_version"] = normalized_meta.get("data_version") or first_value("result_hash", "data_version", "schema_hash")

    result = dict(payload)
    result["meta"] = normalized_meta
    for key in (
        "source_type",
        "data_origin",
        "source_name",
        "domain",
        "run_id",
        "generated_at",
        "updated_at",
        "valid_from",
        "valid_to",
        "model_version",
        "feature_version",
        "schema_hash",
        "data_version",
        "freshness_status",
        "is_stale",
        "stale_reason",
        "staleness_reason",
        "simulation",
        "degraded",
        "availability",
        "unavailable_reason",
    ):
        result[key] = normalized_meta.get(key)
    return result


def unavailable_payload(
    domain: str,
    reason: str,
    *,
    message: str,
    run_id: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    data: Any = None,
) -> dict[str, Any]:
    meta = source_meta(
        SourceType.UNAVAILABLE,
        domain,
        run_id=run_id,
        unavailable_reason=reason,
        evidence=evidence,
    )
    return attach_source_meta(
        {
            "available": False,
            "data": data,
            "message": message,
        },
        meta,
    )


def _forecast_stale(run: dict[str, Any], *, historical: bool) -> tuple[bool, str | None, str | None]:
    if historical:
        return True, "historical_run", None
    now = datetime.now(timezone.utc)
    forecast_end = _datetime(run.get("forecast_end_at"))
    generated = _datetime(run.get("finished_at") or run.get("created_at"))
    if forecast_end is not None:
        expected = forecast_end + timedelta(hours=1)
        return now > expected, "forecast_window_expired" if now > expected else None, _iso(expected)
    if generated is not None:
        expected = generated + timedelta(hours=36)
        return now > expected, "generated_at_older_than_36h" if now > expected else None, _iso(expected)
    return True, "generated_at_missing", None


def resolve_forecast_source(
    run_id: str | None = "latest",
    *,
    domain: str = "electricity_day_ahead_price",
    engine=None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    _validate_domain(domain)
    if domain != "electricity_day_ahead_price":
        meta = source_meta(
            SourceType.UNAVAILABLE,
            domain,
            unavailable_reason="domain_not_supported_by_forecast_results",
        )
        return {}, [], meta

    latest = latest_successful_run(engine=engine)
    requested = str(run_id or "latest").strip()
    run = latest if requested in {"", "latest", "latest_success"} else get_forecast_run(requested, engine=engine)
    if not run:
        meta = source_meta(
            SourceType.UNAVAILABLE,
            domain,
            run_id=None if requested in {"", "latest", "latest_success"} else requested,
            unavailable_reason="no_successful_run" if requested in {"", "latest", "latest_success"} else "run_not_found",
            evidence=[{"table": "forecast_runs", "selection": requested or "latest_success"}],
        )
        return {}, [], meta

    resolved_run_id = str(run.get("run_id") or requested)
    if str(run.get("status") or "").lower() != "success":
        meta = source_meta(
            SourceType.UNAVAILABLE,
            domain,
            run_id=resolved_run_id,
            generated_at=run.get("finished_at") or run.get("created_at"),
            model_version=run.get("model_version"),
            feature_version=run.get("feature_version"),
            schema_hash=run.get("schema_hash"),
            unavailable_reason="run_not_successful",
            evidence=[{"table": "forecast_runs", "run_id": resolved_run_id, "status": run.get("status")}],
        )
        return run, [], meta

    rows = load_forecast_results(resolved_run_id, engine=engine)
    if len(rows) != 24:
        meta = source_meta(
            SourceType.UNAVAILABLE,
            domain,
            run_id=resolved_run_id,
            generated_at=run.get("finished_at") or run.get("created_at"),
            model_version=run.get("model_version"),
            feature_version=run.get("feature_version"),
            schema_hash=run.get("schema_hash"),
            unavailable_reason="result_count_invalid",
            evidence=[{"table": "forecast_results", "run_id": resolved_run_id, "record_count": len(rows)}],
        )
        return run, [], meta

    historical = bool(latest and resolved_run_id != str(latest.get("run_id")))
    is_stale, stale_reason, expected_refresh_at = _forecast_stale(run, historical=historical)
    meta = source_meta(
        SourceType.HISTORICAL if historical else SourceType.REAL,
        domain,
        run_id=resolved_run_id,
        source_name="postgresql.forecast_runs+forecast_results",
        generated_at=run.get("finished_at") or run.get("created_at"),
        updated_at=run.get("finished_at") or run.get("created_at"),
        valid_from=run.get("forecast_start_at"),
        valid_to=run.get("forecast_end_at"),
        model_version=run.get("model_version"),
        feature_version=run.get("feature_version"),
        schema_hash=run.get("schema_hash"),
        data_version=run.get("result_hash") or run.get("schema_hash"),
        is_stale=is_stale,
        stale_reason=stale_reason,
        expected_refresh_at=expected_refresh_at,
        evidence=[
            {"table": "forecast_runs", "run_id": resolved_run_id, "result_hash": run.get("result_hash")},
            {"table": "forecast_results", "run_id": resolved_run_id, "record_count": 24},
        ],
    )
    return run, rows, meta


def forecast_context_payload(
    run_id: str | None = "latest",
    *,
    domain: str = "electricity_day_ahead_price",
    engine=None,
) -> dict[str, Any]:
    run, rows, meta = resolve_forecast_source(run_id, domain=domain, engine=engine)
    if not rows:
        return attach_source_meta(
            {
                "available": False,
                "data": None,
                "message": "当前无可用真实预测。",
                "action": "执行预测任务或查看明确标识的历史批次。",
            },
            meta,
        )
    return attach_source_meta(
        {
            "available": True,
            "data": {
                "record_count": len(rows),
                "forecast_start_at": run.get("forecast_start_at"),
                "forecast_end_at": run.get("forecast_end_at"),
                "status": run.get("status"),
            },
        },
        meta,
    )


_TOOL_DOMAINS = {
    "get_forecast_metrics": "electricity_day_ahead_price",
    "get_high_risk_hours": "electricity_day_ahead_price",
    "explain_low_price_hour": "electricity_day_ahead_price",
    "explain_high_price_hour": "electricity_day_ahead_price",
    "get_storage_discharge_windows": "strategy",
    "get_storage_charge_windows": "strategy",
    "get_weather_summary": "weather",
    "get_load_summary": "forecast_load",
    "get_report_summary": "report",
    "get_model_error_summary": "model_registry",
    "get_data_freshness": "data_quality",
    "query_business_data": "data_quality",
    "get_current_date_context": "system",
}


def normalize_tool_result(name: str, output: dict[str, Any], *, requested_run_id: str | None = None) -> dict[str, Any]:
    result = dict(output or {})
    domain = _TOOL_DOMAINS.get(name, "system")
    available = bool(result.get("available", True))
    if domain in {"electricity_day_ahead_price", "strategy"}:
        _, _, base_meta = resolve_forecast_source(requested_run_id or result.get("run_id") or "latest")
        meta = dict(base_meta)
        if available and meta.get("source_type") in {SourceType.REAL.value, SourceType.HISTORICAL.value}:
            meta["source_type"] = SourceType.DERIVED.value
            meta["evidence"] = list(meta.get("evidence") or []) + [{"tool": name, "derivation": "read_only"}]
        elif not available:
            meta["source_type"] = SourceType.UNAVAILABLE.value
            meta["unavailable_reason"] = result.get("unavailable_reason") or meta.get("unavailable_reason") or "tool_no_data"
    else:
        raw_type = str(result.get("source_type") or "")
        source_type = raw_type if raw_type in {item.value for item in SourceType} else (
            SourceType.DERIVED.value if available else SourceType.UNAVAILABLE.value
        )
        meta = source_meta(
            source_type,
            domain,
            run_id=result.get("run_id"),
            generated_at=result.get("generated_at"),
            evidence=list(result.get("evidence") or []),
            unavailable_reason=None if available else result.get("unavailable_reason") or "tool_no_data",
            fallback_reason=result.get("fallback_reason"),
        )
    result["available"] = available and meta.get("source_type") != SourceType.UNAVAILABLE.value
    return attach_source_meta(result, meta)
