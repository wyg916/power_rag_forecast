from __future__ import annotations

import re
from typing import Any

from ..data_access import jsonable
from ..data_registry import DATASET_REGISTRY, DatasetSpec, find_datasets, resolve_dataset_reference
from .dataset_query_service import (
    DatasetQueryError,
    dataset_freshness,
    list_registered_datasets,
    query_dataset_rows,
    query_dataset_summary,
)


DATE_RE = re.compile(r"(20\d{2})[-/年](\d{1,2})(?:[-/月](\d{1,2}))?")
SENSITIVE_REFERENCES = frozenset(
    {
        "alembic_version",
        "audit_logs",
        "information_schema",
        "permissions",
        "pg_authid",
        "pg_catalog",
        "roles",
        "system_runtime_config",
        "task_logs",
        "task_runs",
        "user_roles",
        "users",
    }
)


def _extract_dates(question: str) -> list[str]:
    values: list[str] = []
    for year, month, day in DATE_RE.findall(question or ""):
        values.append(f"{year}-{int(month):02d}-{int(day or 1):02d}")
    return values[:2]


def _limit(question: str, requested: int | None) -> int:
    if requested is not None:
        return max(1, min(int(requested), 50))
    match = re.search(r"(?:前|最新|最近)?\s*(\d{1,3})\s*(?:条|行|个|笔)", question or "")
    return max(1, min(int(match.group(1)), 50)) if match else 5


def _requested_specs(question: str, references: list[str] | None) -> list[DatasetSpec]:
    specs: list[DatasetSpec] = []
    for value in references or []:
        spec = resolve_dataset_reference(value, ai_only=True)
        if spec and spec.dataset_id not in {item.dataset_id for item in specs}:
            specs.append(spec)
    if specs:
        return specs[:3]
    lowered = str(question or "").lower()
    scored: list[tuple[int, DatasetSpec]] = []
    for spec in find_datasets(ai_only=True):
        score = 0
        if spec.display_name.lower() in lowered:
            score += 4
        for alias in spec.aliases:
            if str(alias).lower() in lowered:
                score += 2
        if spec.business_domain.lower() in lowered:
            score += 1
        if score:
            scored.append((score, spec))
    scored.sort(key=lambda item: (-item[0], item[1].dataset_id))
    return [spec for _, spec in scored[:3]]


def _looks_like(question: str, terms: list[str]) -> bool:
    compact = re.sub(r"\s+", "", str(question or "").lower())
    return any(term.lower().replace(" ", "") in compact for term in terms)


def _public_fields(spec: DatasetSpec, question: str, requested_fields: list[str] | None) -> list[str]:
    allowed = spec.field_map
    selected = [str(item).strip().lower() for item in (requested_fields or []) if str(item).strip().lower() in allowed]
    lowered = str(question or "").lower()
    token_map = {
        "电价": ["day_ahead_price", "real_time_price", "marginal_price", "predicted_price", "corrected_price"],
        "负荷": ["actual_load_mw", "forecast_load_mw"],
        "天气": ["temperature_c", "humidity_pct", "wind_speed"],
        "温度": ["temperature_c"],
        "风险": ["risk_level", "spike_probability"],
        "误差": ["absolute_error", "percentage_error"],
        "重要性": ["feature_name", "importance_score", "importance_rank"],
    }
    for token, candidates in token_map.items():
        if token in lowered:
            selected.extend(item for item in candidates if item in allowed)
    if spec.default_sort in allowed:
        selected.insert(0, spec.default_sort)
    return list(dict.fromkeys(selected))[:8] or [field.field_id for field in spec.fields[:6]]


def _blocked_reference(question: str, references: list[str] | None) -> str:
    values = [str(item or "").strip().lower() for item in (references or [])]
    lowered = str(question or "").lower()
    return next((value for value in SENSITIVE_REFERENCES if value in values or value in lowered), "")


def _catalog_result() -> dict[str, Any]:
    datasets = list_registered_datasets(ai_only=True)["datasets"]
    records = [
        {
            "dataset_id": item["dataset_id"],
            "display_name": item["display_name"],
            "business_domain": item["business_domain"],
            "default_sort": item["default_sort"],
        }
        for item in datasets
    ]
    return {
        "tool": "query_business_data",
        "available": True,
        "safe": True,
        "query_type": "data_catalog_list",
        "dataset_id": "registered_business_datasets",
        "display_name": "受控业务数据集",
        "fields": ["dataset_id", "display_name", "business_domain", "default_sort"],
        "records": records,
        "columns": ["dataset_id", "display_name", "business_domain", "default_sort"],
        "row_count": len(records),
        "time_range": {"start": None, "end": None, "field": ""},
        "query_summary": "列出允许 AI 访问的已注册业务数据集；不枚举数据库对象。",
        "not_found_reason": "",
        "evidence": [{"source": "dataset_registry", "operation": "catalog_list", "available": True}],
    }


def _empty_result() -> dict[str, Any]:
    allowed_ids = [spec.dataset_id for spec in find_datasets(ai_only=True)]
    report = dataset_freshness(allowed_ids)
    records = [item for item in report["items"] if item.get("available") and int(item.get("row_count") or 0) == 0]
    return {
        "tool": "query_business_data",
        "available": True,
        "safe": True,
        "query_type": "empty_dataset_scan",
        "dataset_id": "registered_business_datasets",
        "display_name": "受控业务数据集",
        "fields": ["dataset_id", "display_name", "status", "row_count"],
        "records": records,
        "columns": ["dataset_id", "display_name", "status", "row_count"],
        "row_count": len(records),
        "time_range": {"start": None, "end": None, "field": ""},
        "query_summary": "检查已注册且允许 AI 访问的数据集是否为空。",
        "not_found_reason": "" if records else "未发现已注册且当前为空的数据集。",
        "evidence": [{"source": "dataset_registry", "operation": "empty_dataset_scan", "available": True}],
    }


def _readiness_result() -> dict[str, Any]:
    required = ["market_price_history", "load_history", "weather_observations", "forecast_output"]
    report = dataset_freshness(required)
    records = report["items"]
    ready = all(item.get("available") and int(item.get("row_count") or 0) > 0 for item in records)
    return {
        "tool": "query_business_data",
        "available": True,
        "safe": True,
        "query_type": "prediction_readiness",
        "readiness_status": "ready" if ready else "partial",
        "dataset_id": "prediction_readiness",
        "display_name": "预测数据支撑检查",
        "fields": ["dataset_id", "datetime_field", "min_datetime", "max_datetime", "row_count", "status"],
        "records": records,
        "columns": ["dataset_id", "display_name", "status", "datetime_field", "min_datetime", "max_datetime", "row_count"],
        "row_count": len(records),
        "time_range": {"start": None, "end": None, "field": "per_dataset_time_field"},
        "query_summary": "按固定 query_id 检查预测依赖数据集的新鲜度和记录数。",
        "not_found_reason": "" if ready else "部分预测支撑数据集不可用或为空。",
        "evidence": [{"source": "dataset_registry", "operation": "prediction_readiness", "available": True}],
    }


def query_business_data(
    question: str,
    tables: list[str] | None = None,
    dataset_ids: list[str] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    references = dataset_ids or tables or []
    blocked = _blocked_reference(question, references)
    if blocked:
        return {
            "tool": "query_business_data",
            "available": False,
            "safe": False,
            "dataset_id": "",
            "fields": [],
            "records": [],
            "columns": [],
            "row_count": 0,
            "time_range": {"start": None, "end": None, "field": ""},
            "query_summary": "请求涉及敏感或系统对象，已在数据集注册表边界拒绝。",
            "not_found_reason": "请求对象不属于允许的业务数据集。",
            "evidence": [{"source": "dataset_registry", "operation": "deny_unregistered", "available": False}],
        }
    if _looks_like(question, ["核心业务表", "有哪些表", "数据目录", "数据库有哪些"]):
        return jsonable(_catalog_result())
    if _looks_like(question, ["哪些表为空", "哪些数据集为空", "数据集当前为空", "空表", "空数据集"]):
        return jsonable(_empty_result())
    if _looks_like(question, ["数据支撑预测", "足够支撑预测"]):
        return jsonable(_readiness_result())
    specs = _requested_specs(question, references)
    if not specs:
        return {
            "tool": "query_business_data",
            "available": False,
            "safe": False,
            "dataset_id": "",
            "fields": [],
            "records": [],
            "columns": [],
            "row_count": 0,
            "time_range": {"start": None, "end": None, "field": ""},
            "query_summary": "未识别到已注册业务数据集。",
            "not_found_reason": "请使用数据集名称或明确业务域；系统不会按数据库对象名自动搜索。",
            "evidence": [],
        }
    spec = specs[0]
    selected_fields = _public_fields(spec, question, fields)
    dates = _extract_dates(question)
    try:
        if _looks_like(question, ["多少条", "几条", "记录数", "总数", "count"]):
            result = query_dataset_summary(
                spec.dataset_id,
                query_id="count",
                start=dates[0] if dates else None,
                end=dates[1] if len(dates) > 1 else None,
            )
            query_type = "count"
        elif _looks_like(question, ["平均", "均值", "均价", "最高", "最低", "avg", "max", "min"]):
            metric = next(
                (field_id for field_id in selected_fields if spec.field_map[field_id].data_type in {"integer", "number"}),
                None,
            )
            if metric is None:
                raise DatasetQueryError("metric_field_not_allowed", "未识别到允许聚合的数值字段。")
            result = query_dataset_summary(
                spec.dataset_id,
                query_id="numeric_summary",
                metric_field=metric,
                start=dates[0] if dates else None,
                end=dates[1] if len(dates) > 1 else None,
            )
            query_type = "numeric_summary"
        else:
            result = query_dataset_rows(
                spec.dataset_id,
                sort=spec.default_sort,
                direction=spec.default_sort_direction,
                page=1,
                page_size=min(_limit(question, limit), spec.max_page_size),
            )
            query_type = "latest_rows"
    except DatasetQueryError as exc:
        return {
            "tool": "query_business_data",
            "available": False,
            "safe": False,
            "dataset_id": spec.dataset_id,
            "display_name": spec.display_name,
            "fields": selected_fields,
            "records": [],
            "columns": [],
            "row_count": 0,
            "time_range": {"start": dates[0] if dates else None, "end": dates[1] if len(dates) > 1 else None, "field": ""},
            "query_summary": "受控查询未执行。",
            "not_found_reason": exc.message,
            "evidence": [{"source": spec.dataset_id, "operation": "controlled_query", "available": False}],
        }
    result.update(
        {
            "tool": "query_business_data",
            "safe": True,
            "query_type": query_type,
            "dataset_id": spec.dataset_id,
            "display_name": spec.display_name,
            "fields": selected_fields,
            "query_summary": f"通过服务端固定模板执行 {query_type}；客户端输入未成为 SQL。",
            "evidence": [
                {
                    "source": spec.dataset_id,
                    "fields": selected_fields,
                    "operation": f"controlled_{query_type}",
                    "available": bool(result.get("available")),
                }
            ],
        }
    )
    return jsonable(result)


def get_data_freshness(domain: str = "weather", tables: list[str] | None = None, dataset_ids: list[str] | None = None, **_: Any) -> dict[str, Any]:
    domain_defaults = {
        "weather": "weather_observations",
        "da_price": "day_ahead_price",
        "rt_price": "real_time_price",
        "load": "actual_load",
        "forecast_load": "load_forecast",
    }
    references = dataset_ids or tables or []
    specs = _requested_specs("", references)
    selected = [spec.dataset_id for spec in specs] or [domain_defaults.get(domain, "weather_observations")]
    try:
        report = dataset_freshness(selected)
    except DatasetQueryError as exc:
        return {"tool": "get_data_freshness", "available": False, "domain": domain, "message": exc.message, "evidence": []}
    items = report["items"]
    if len(items) > 1:
        return {
            "tool": "get_data_freshness",
            "available": any(item.get("available") for item in items),
            "domain": "registered_datasets",
            "dataset_id": ",".join(selected),
            "multi_dataset": True,
            "items": items,
            "status": "ok" if all(item.get("available") for item in items) else "partial",
            "evidence": [{"source": item["dataset_id"], "operation": "controlled_freshness", "available": item.get("available")} for item in items],
        }
    item = items[0]
    return {
        "tool": "get_data_freshness",
        "available": bool(item.get("available")),
        "domain": domain,
        "dataset_id": item["dataset_id"],
        "datetime_field": item.get("datetime_field"),
        "min_datetime": item.get("min_datetime"),
        "max_datetime": item.get("max_datetime"),
        "row_count": item.get("row_count"),
        "missing_count": item.get("missing_count"),
        "status": item.get("status"),
        "query_summary": item.get("query_summary"),
        "evidence": [{"source": item["dataset_id"], "operation": "controlled_freshness", "available": item.get("available")}],
    }
