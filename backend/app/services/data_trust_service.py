from __future__ import annotations

from typing import Any

from ..data_registry import legacy_catalog_by_object, resolve_dataset_reference
from ..db.session import get_engine as database_engine
from .controlled_business_query_service import query_business_data
from .dataset_query_service import dataset_fields, dataset_freshness, list_registered_datasets


# Internal compatibility only. Public responses are produced from DatasetSpec.public_dict()
# and never expose these physical-object keys.
CORE_DATASETS = legacy_catalog_by_object()


def validate_read_only_sql(sql: str) -> tuple[bool, str, list[str], str]:
    del sql
    return False, "", [], "任意 SQL 能力已永久禁用，请使用服务端注册的数据集和固定查询模板。"


def execute_read_only_sql(sql: str, params: dict[str, Any] | None = None, limit: int = 100) -> dict[str, Any]:
    del sql, params, limit
    return {
        "available": False,
        "safe": False,
        "tables": [],
        "columns": [],
        "records": [],
        "row_count": 0,
        "not_found_reason": "任意 SQL 能力已永久禁用，请使用服务端注册的数据集和固定查询模板。",
        "query_summary": "请求在进入数据库驱动前被拒绝。",
    }


def get_data_catalog(search: str | None = None, include_runtime: bool = False) -> dict[str, Any]:
    return list_registered_datasets(search=search, include_runtime=include_runtime)


def get_field_mappings(table: str | None = None, search: str | None = None) -> dict[str, Any]:
    spec = resolve_dataset_reference(str(table or ""))
    if spec is None:
        return {
            "available": False,
            "dataset_id": "",
            "fields": [],
            "total": 0,
            "message": "数据集未注册或不可访问。",
        }
    return dataset_fields(spec.dataset_id, search=search)


def get_data_freshness_report(tables: list[str] | None = None) -> dict[str, Any]:
    dataset_ids: list[str] = []
    for reference in tables or []:
        spec = resolve_dataset_reference(reference)
        if spec is None:
            return {
                "available": False,
                "catalog_version": "day4_dataset_registry_v1",
                "items": [],
                "message": "数据集未注册或不可访问。",
            }
        dataset_ids.append(spec.dataset_id)
    return dataset_freshness(dataset_ids or None)


__all__ = [
    "CORE_DATASETS",
    "database_engine",
    "execute_read_only_sql",
    "get_data_catalog",
    "get_data_freshness_report",
    "get_field_mappings",
    "query_business_data",
    "validate_read_only_sql",
]
