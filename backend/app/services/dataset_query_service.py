from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import csv
from io import StringIO
import logging
import os
import re
from typing import Any, Literal

from sqlalchemy import String, and_, bindparam, case, cast, column, func, inspect, or_, select, table
from sqlalchemy.engine import Engine

from ..data_access import database_engine, jsonable
from ..data_registry import DATASET_REGISTRY, DatasetField, DatasetRegistryError, DatasetSpec, find_datasets, get_dataset


logger = logging.getLogger(__name__)
FilterOperator = Literal["eq", "contains", "gte", "lte"]
SortDirection = Literal["asc", "desc"]
QUERY_TIMEOUT_MS = 5000
MAX_SEARCH_LENGTH = 256
_TEST_SCHEMA_RE = re.compile(r"^beta10d_day3_close_[a-z0-9_]+$")


class DatasetQueryError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _spec(dataset_id: str) -> DatasetSpec:
    try:
        return get_dataset(dataset_id)
    except DatasetRegistryError as exc:
        raise DatasetQueryError("dataset_not_allowed", "数据集未注册或不可访问。", status_code=404) from exc


def _database_schema() -> str:
    schema = os.environ.get("BETA10D_TEST_SCHEMA", "").strip()
    mode = os.environ.get("BETA10D_TEST_DATABASE_MODE", "").strip()
    if mode == "isolated-schema":
        if not _TEST_SCHEMA_RE.fullmatch(schema):
            raise DatasetQueryError("invalid_test_schema", "隔离测试 Schema 未通过前缀门禁。", status_code=503)
        return schema
    return "public"


def _sa_table(spec: DatasetSpec):
    return table(spec.object_name, *(column(field.column_name) for field in spec.fields), schema=_database_schema())


def _coerce_filter_value(field: DatasetField, value: str) -> Any:
    raw = str(value or "").strip()
    if not raw or len(raw) > MAX_SEARCH_LENGTH or any(ord(char) < 32 for char in raw):
        raise DatasetQueryError("invalid_filter_value", "过滤值为空、过长或包含控制字符。")
    if field.data_type == "integer":
        try:
            return int(raw)
        except ValueError as exc:
            raise DatasetQueryError("invalid_filter_value", "过滤值不是有效整数。") from exc
    if field.data_type == "number":
        try:
            return Decimal(raw)
        except InvalidOperation as exc:
            raise DatasetQueryError("invalid_filter_value", "过滤值不是有效数值。") from exc
    if field.data_type == "boolean":
        lowered = raw.lower()
        if lowered in {"1", "true", "yes"}:
            return True
        if lowered in {"0", "false", "no"}:
            return False
        raise DatasetQueryError("invalid_filter_value", "过滤值不是有效布尔值。")
    if field.data_type == "datetime":
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DatasetQueryError("invalid_filter_value", "过滤值不是有效 ISO 日期时间。") from exc
    return raw


def _filter_clause(spec: DatasetSpec, source, field_id: str | None, operator: str, value: str | None):
    if not field_id and value in (None, ""):
        return None
    field = spec.field_map.get(str(field_id or "").strip().lower())
    if field is None or not field.filterable:
        raise DatasetQueryError("filter_field_not_allowed", "过滤字段不在数据集白名单中。")
    if operator not in {"eq", "contains", "gte", "lte"}:
        raise DatasetQueryError("filter_operator_not_allowed", "过滤操作符不在白名单中。")
    if operator == "contains" and field.data_type != "string":
        raise DatasetQueryError("filter_operator_not_allowed", "contains 仅允许字符串字段。")
    coerced = _coerce_filter_value(field, str(value or ""))
    db_column = source.c[field.column_name]
    if operator == "contains":
        return cast(db_column, String).ilike(bindparam("filter_pattern")), {"filter_pattern": f"%{coerced}%"}
    bound = bindparam("filter_value", value=coerced)
    return {
        "eq": db_column == bound,
        "gte": db_column >= bound,
        "lte": db_column <= bound,
    }[operator], {"filter_value": coerced}


def _search_clause(spec: DatasetSpec, source, search: str | None):
    keyword = str(search or "").strip()
    if not keyword:
        return None, {}
    if len(keyword) > MAX_SEARCH_LENGTH or any(ord(char) < 32 for char in keyword):
        raise DatasetQueryError("invalid_search", "搜索词过长或包含控制字符。")
    searchable = [field for field in spec.fields if field.searchable]
    if not searchable:
        raise DatasetQueryError("search_not_supported", "该数据集不支持全文搜索。")
    return (
        or_(*(cast(source.c[field.column_name], String).ilike(bindparam("search_pattern")) for field in searchable)),
        {"search_pattern": f"%{keyword}%"},
    )


def _apply_timeout(connection) -> None:
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql(f"SET LOCAL statement_timeout = '{QUERY_TIMEOUT_MS}ms'")


def validate_registry_against_database(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    schema = _database_schema()
    tables = set(inspector.get_table_names(schema=schema))
    views = set(inspector.get_view_names(schema=schema))
    errors: list[str] = []
    for spec in DATASET_REGISTRY.values():
        available = tables if spec.object_type == "table" else views
        if spec.object_name not in available:
            errors.append(f"{spec.dataset_id}: missing {spec.object_type}")
            continue
        actual_columns = {str(item.get("name")) for item in inspector.get_columns(spec.object_name, schema=schema)}
        missing = sorted(set(spec.column_map) - actual_columns)
        if missing:
            errors.append(f"{spec.dataset_id}: missing fields {','.join(missing)}")
    if errors:
        raise DatasetRegistryError("数据库对象与数据集注册表不一致：" + "；".join(errors))
    return {"dataset_count": len(DATASET_REGISTRY), "validated": True}


def list_registered_datasets(search: str | None = None, *, include_runtime: bool = False, ai_only: bool = False) -> dict[str, Any]:
    specs = find_datasets(search, ai_only=ai_only)
    existing: set[str] | None = None
    if include_runtime:
        engine = database_engine()
        if engine is not None:
            inspector = inspect(engine)
            schema = _database_schema()
            existing = set(inspector.get_table_names(schema=schema)) | set(inspector.get_view_names(schema=schema))
    datasets = [spec.public_dict(exists=(spec.object_name in existing) if existing is not None else None) for spec in specs]
    return {
        "available": bool(datasets),
        "catalog_version": "day4_dataset_registry_v1",
        "datasets": datasets,
        "total": len(datasets),
    }


def dataset_fields(dataset_id: str, search: str | None = None) -> dict[str, Any]:
    spec = _spec(dataset_id)
    keyword = str(search or "").strip().lower()
    fields = [field.public_dict() for field in spec.fields if not keyword or keyword in f"{field.field_id} {field.display_name} {field.description}".lower()]
    return {
        "available": bool(fields),
        "dataset_id": spec.dataset_id,
        "display_name": spec.display_name,
        "fields": fields,
        "total": len(fields),
    }


def query_dataset_rows(
    dataset_id: str,
    *,
    search: str | None = None,
    filter_field: str | None = None,
    filter_operator: FilterOperator = "eq",
    filter_value: str | None = None,
    sort: str | None = None,
    direction: SortDirection | None = None,
    page: int = 1,
    page_size: int = 20,
    engine: Engine | None = None,
) -> dict[str, Any]:
    spec = _spec(dataset_id)
    safe_page = max(1, int(page or 1))
    safe_page_size = int(page_size or 20)
    if safe_page_size < 1 or safe_page_size > spec.max_page_size:
        raise DatasetQueryError("page_size_not_allowed", f"page_size 必须在 1..{spec.max_page_size}。")
    sort_id = str(sort or spec.default_sort).strip().lower()
    sort_field = spec.field_map.get(sort_id)
    if sort_field is None or not sort_field.sortable:
        raise DatasetQueryError("sort_field_not_allowed", "排序字段不在数据集白名单中。")
    sort_direction = str(direction or spec.default_sort_direction).strip().lower()
    if sort_direction not in {"asc", "desc"}:
        raise DatasetQueryError("sort_direction_not_allowed", "排序方向只允许 asc 或 desc。")
    active_engine = engine or database_engine()
    if active_engine is None:
        raise DatasetQueryError("database_unavailable", "数据库连接不可用。", status_code=503)
    source = _sa_table(spec)
    selected = [source.c[field.column_name].label(field.field_id) for field in spec.fields]
    clauses = []
    params: dict[str, Any] = {}
    filter_result = _filter_clause(spec, source, filter_field, str(filter_operator), filter_value)
    if filter_result:
        clause, values = filter_result
        clauses.append(clause)
        params.update(values)
    search_clause, search_params = _search_clause(spec, source, search)
    if search_clause is not None:
        clauses.append(search_clause)
        params.update(search_params)
    where_clause = and_(*clauses) if clauses else None
    count_stmt = select(func.count()).select_from(source)
    data_stmt = select(*selected).select_from(source)
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
        data_stmt = data_stmt.where(where_clause)
    sort_expression = source.c[sort_field.column_name]
    data_stmt = data_stmt.order_by(sort_expression.asc() if sort_direction == "asc" else sort_expression.desc())
    offset = (safe_page - 1) * safe_page_size
    data_stmt = data_stmt.limit(safe_page_size).offset(offset)
    try:
        with active_engine.connect() as connection:
            _apply_timeout(connection)
            total = int(connection.execute(count_stmt, params).scalar_one())
            rows = [jsonable(dict(row)) for row in connection.execute(data_stmt, params).mappings()]
    except DatasetQueryError:
        raise
    except Exception as exc:
        logger.warning("dataset query failed: dataset_id=%s error_type=%s", spec.dataset_id, type(exc).__name__)
        raise DatasetQueryError("query_failed", "数据集查询失败。", status_code=503) from exc
    return {
        "available": True,
        "dataset_id": spec.dataset_id,
        "display_name": spec.display_name,
        "object_type": spec.object_type,
        "columns": [field.public_dict() for field in spec.fields],
        "records": rows,
        "total": total,
        "limit": safe_page_size,
        "offset": offset,
        "pagination": {"page": safe_page, "page_size": safe_page_size, "total": total},
        "search_applied": bool(str(search or "").strip()),
        "filter": {"field": filter_field or "", "operator": filter_operator} if filter_field else {},
        "order_by": sort_id,
        "order_direction": sort_direction,
    }


def query_dataset_summary(
    dataset_id: str,
    *,
    query_id: Literal["count", "numeric_summary"],
    metric_field: str | None = None,
    start: str | None = None,
    end: str | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    spec = _spec(dataset_id)
    if not spec.ai_allowed:
        raise DatasetQueryError("ai_access_not_allowed", "该数据集不允许 AI 工具访问。", status_code=403)
    source = _sa_table(spec)
    active_engine = engine or database_engine()
    if active_engine is None:
        raise DatasetQueryError("database_unavailable", "数据库连接不可用。", status_code=503)
    time_field = next((field for field in spec.fields if field.data_type == "datetime" and field.filterable), None)
    clauses = []
    params: dict[str, Any] = {}
    for key, value, op in (("start", start, "gte"), ("end", end, "lte")):
        if value:
            if time_field is None:
                raise DatasetQueryError("date_filter_not_supported", "该数据集不支持日期范围。")
            coerced = _coerce_filter_value(time_field, value)
            bound = bindparam(key, value=coerced)
            clauses.append(source.c[time_field.column_name] >= bound if op == "gte" else source.c[time_field.column_name] <= bound)
            params[key] = coerced
    if query_id == "count":
        stmt = select(func.count().label("row_count")).select_from(source)
        public_fields = ["row_count"]
    else:
        field = spec.field_map.get(str(metric_field or "").strip().lower())
        if field is None or field.data_type not in {"integer", "number"}:
            raise DatasetQueryError("metric_field_not_allowed", "聚合字段不在数值字段白名单中。")
        metric = source.c[field.column_name]
        stmt = select(
            func.count().label("row_count"),
            func.avg(metric).label("average"),
            func.min(metric).label("minimum"),
            func.max(metric).label("maximum"),
        ).select_from(source)
        public_fields = ["row_count", "average", "minimum", "maximum"]
    if clauses:
        stmt = stmt.where(and_(*clauses))
    try:
        with active_engine.connect() as connection:
            _apply_timeout(connection)
            record = jsonable(dict(connection.execute(stmt, params).mappings().one()))
    except Exception as exc:
        logger.warning("dataset summary failed: dataset_id=%s query_id=%s error_type=%s", spec.dataset_id, query_id, type(exc).__name__)
        raise DatasetQueryError("query_failed", "数据集汇总查询失败。", status_code=503) from exc
    return {
        "available": True,
        "safe": True,
        "query_id": query_id,
        "dataset_id": spec.dataset_id,
        "display_name": spec.display_name,
        "fields": public_fields,
        "records": [record],
        "row_count": int(record.get("row_count") or 0),
        "time_range": {"start": start, "end": end, "field": time_field.field_id if time_field else ""},
    }


def dataset_freshness(dataset_ids: list[str] | None = None, *, engine: Engine | None = None) -> dict[str, Any]:
    requested = [str(item or "").strip().lower() for item in (dataset_ids or []) if str(item or "").strip()]
    if requested:
        unknown = [item for item in requested if item not in DATASET_REGISTRY]
        if unknown:
            raise DatasetQueryError("dataset_not_allowed", "一个或多个数据集未注册或不可访问。", status_code=404)
        specs = [DATASET_REGISTRY[item] for item in dict.fromkeys(requested)]
    else:
        specs = list(DATASET_REGISTRY.values())
    active_engine = engine or database_engine()
    if active_engine is None:
        raise DatasetQueryError("database_unavailable", "数据库连接不可用。", status_code=503)
    inspector = inspect(active_engine)
    schema = _database_schema()
    available_objects = set(inspector.get_table_names(schema=schema)) | set(inspector.get_view_names(schema=schema))
    items: list[dict[str, Any]] = []
    for spec in specs:
        if spec.object_name not in available_objects:
            items.append(
                {
                    "dataset_id": spec.dataset_id,
                    "display_name": spec.display_name,
                    "available": False,
                    "status": "unavailable",
                    "row_count": 0,
                    "not_found_reason": "已注册数据集当前不可用。",
                }
            )
            continue
        source = _sa_table(spec)
        time_field = next((field for field in spec.fields if field.data_type == "datetime"), None)
        missing_parts = [case((source.c[field.column_name].is_(None), 1), else_=0) for field in spec.fields]
        selected = [
            func.count().label("row_count"),
            sum((func.sum(part) for part in missing_parts), start=0).label("missing_count"),
        ]
        if time_field:
            selected.extend(
                [
                    func.min(source.c[time_field.column_name]).label("min_datetime"),
                    func.max(source.c[time_field.column_name]).label("max_datetime"),
                ]
            )
        stmt = select(*selected).select_from(source)
        try:
            with active_engine.connect() as connection:
                _apply_timeout(connection)
                row = jsonable(dict(connection.execute(stmt).mappings().one()))
        except Exception as exc:
            logger.warning("dataset freshness failed: dataset_id=%s error_type=%s", spec.dataset_id, type(exc).__name__)
            items.append(
                {
                    "dataset_id": spec.dataset_id,
                    "display_name": spec.display_name,
                    "available": False,
                    "status": "query_error",
                    "row_count": 0,
                    "not_found_reason": "数据集新鲜度查询失败。",
                }
            )
            continue
        row_count = int(row.get("row_count") or 0)
        items.append(
            {
                "dataset_id": spec.dataset_id,
                "display_name": spec.display_name,
                "available": True,
                "status": "ok" if row_count else "empty",
                "datetime_field": time_field.field_id if time_field else "",
                "min_datetime": row.get("min_datetime"),
                "max_datetime": row.get("max_datetime"),
                "row_count": row_count,
                "missing_count": int(row.get("missing_count") or 0),
                "fields": [field.field_id for field in spec.fields],
                "query_summary": "按注册字段执行受控 count/min/max/空值汇总。",
                "not_found_reason": "" if row_count else "数据集存在但当前没有记录。",
            }
        )
    return {
        "available": any(item.get("available") for item in items),
        "catalog_version": "day4_dataset_registry_v1",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
        "summary": {
            "dataset_count": len(items),
            "available_count": sum(1 for item in items if item.get("available")),
            "empty_count": sum(1 for item in items if item.get("status") == "empty"),
            "unavailable_count": sum(1 for item in items if not item.get("available")),
        },
    }


def dataset_quality_report(*, engine: Engine | None = None) -> dict[str, Any]:
    freshness = dataset_freshness(engine=engine)
    items: list[dict[str, Any]] = []
    for item in freshness["items"]:
        row_count = int(item.get("row_count") or 0)
        spec = DATASET_REGISTRY[str(item["dataset_id"])]
        total_cells = row_count * len(spec.fields)
        missing_count = int(item.get("missing_count") or 0)
        missing_rate = round(missing_count / total_cells * 100, 4) if total_cells else None
        status = str(item.get("status") or "unavailable")
        latest_value = item.get("max_datetime")
        age_hours: float | None = None
        if latest_value not in (None, ""):
            try:
                stamp = latest_value if isinstance(latest_value, datetime) else datetime.fromisoformat(str(latest_value).replace("Z", "+00:00"))
                now = datetime.now(tz=stamp.tzinfo) if stamp.tzinfo else datetime.now()
                age_hours = max(0.0, (now - stamp).total_seconds() / 3600)
            except (TypeError, ValueError):
                age_hours = None
        is_stale = bool(age_hours is not None and age_hours > 48)
        if status == "ok" and is_stale:
            status = "stale"
        freshness_score = (
            max(0.0, 100 - max(0.0, age_hours - 48) * 100 / (48 * 3))
            if age_hours is not None
            else None
        )
        items.append(
            {
                "dataset_id": spec.dataset_id,
                "source_name": spec.display_name,
                "available": bool(item.get("available")),
                "status": status,
                "rows": row_count,
                "missing_values": missing_count,
                "missing_rate": missing_rate,
                "duplicate_rate": None,
                "freshness_score": round(freshness_score, 2) if freshness_score is not None else None,
                "freshness_age_hours": round(age_hours, 2) if age_hours is not None else None,
                "consistency_score": 100.0 if item.get("available") else 0.0,
                "check_pass_rate": None if status != "ok" else 100.0,
                "latest_time": item.get("max_datetime"),
                "message": item.get("not_found_reason") or "基于注册字段执行受控质量汇总。",
                "data_source": f"dataset:{spec.dataset_id}",
                "is_stale": is_stale,
                "stale_reason": (
                    f"latest_record_age_{age_hours:.2f}h_exceeds_48h" if is_stale and age_hours is not None else None
                ),
            }
        )
    exceptions = [item for item in items if item.get("status") != "ok"]
    return {
        "available": any(item.get("available") for item in items),
        "generated_at": freshness["checked_at"],
        "is_stale": any(bool(item.get("is_stale")) for item in items),
        "stale_reason": (
            "one_or_more_datasets_exceed_48h_freshness_threshold"
            if any(bool(item.get("is_stale")) for item in items)
            else None
        ),
        "items": items,
        "exceptions": exceptions,
        "alerts": [
            {
                "alert_id": f"quality:{item['dataset_id']}:{item['status']}",
                "severity": "high" if item["status"] in {"unavailable", "query_error"} else "medium",
                "alert_type": "availability" if not item.get("available") else "empty",
                "object_name": item["dataset_id"],
                "detected_at": freshness["checked_at"],
                "status": "open",
                "source": "dataset_registry",
                "message": item.get("message") or "数据质量异常。",
            }
            for item in exceptions
        ],
        "summary": {
            "source_count": sum(1 for item in items if item.get("available")),
            "checked_source_count": len(items),
            "exception_count": len(exceptions),
            "avg_missing_rate": None,
            "avg_duplicate_rate": None,
            "avg_freshness_score": (
                round(
                    sum(float(item["freshness_score"]) for item in items if item.get("freshness_score") is not None)
                    / sum(1 for item in items if item.get("freshness_score") is not None),
                    2,
                )
                if any(item.get("freshness_score") is not None for item in items)
                else None
            ),
            "avg_consistency_score": None,
            "avg_check_pass_rate": None,
        },
        "data_source": "dataset_registry_controlled_aggregates",
    }


def dataset_status(*, engine: Engine | None = None) -> dict[str, Any]:
    freshness = dataset_freshness(engine=engine)
    return {
        "sources": [
            {
                "dataset_id": item["dataset_id"],
                "name": item["display_name"],
                "status": item["status"],
                "rows": item.get("row_count", 0),
                "latest_time": item.get("max_datetime"),
                "available": item.get("available", False),
            }
            for item in freshness["items"]
        ],
        "generated_at": freshness["checked_at"],
    }


def export_dataset_csv(
    dataset_id: str,
    *,
    search: str | None = None,
    filter_field: str | None = None,
    filter_operator: FilterOperator = "eq",
    filter_value: str | None = None,
    sort: str | None = None,
    direction: SortDirection | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    spec = _spec(dataset_id)
    if not spec.export_allowed:
        raise DatasetQueryError("export_not_allowed", "该数据集不允许导出。", status_code=403)
    payload = query_dataset_rows(
        dataset_id,
        search=search,
        filter_field=filter_field,
        filter_operator=filter_operator,
        filter_value=filter_value,
        sort=sort,
        direction=direction,
        page=1,
        page_size=min(spec.export_max_rows, spec.max_page_size),
        engine=engine,
    )
    records = list(payload["records"])
    target_count = min(int(payload["total"]), spec.export_max_rows)
    next_page = 2
    while len(records) < target_count:
        next_payload = query_dataset_rows(
            dataset_id,
            search=search,
            filter_field=filter_field,
            filter_operator=filter_operator,
            filter_value=filter_value,
            sort=sort,
            direction=direction,
            page=next_page,
            page_size=spec.max_page_size,
            engine=engine,
        )
        if not next_payload["records"]:
            break
        records.extend(next_payload["records"])
        next_page += 1
    records = records[:target_count]
    output = StringIO(newline="")
    field_ids = [field.field_id for field in spec.fields]
    writer = csv.DictWriter(output, fieldnames=field_ids, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    return {
        "available": True,
        "filename": f"{spec.dataset_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        "content": content,
        "row_count": len(records),
        "total": payload["total"],
        "truncated": payload["total"] > len(records),
    }
