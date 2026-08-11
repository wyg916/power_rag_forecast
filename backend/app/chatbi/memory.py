from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from sqlalchemy.engine import Engine

from backend.app.ai.identity_context import IdentityContext
from backend.app.ai_assistant.memory.enterprise_memory import admit_memory, retrieve_memories

from .catalog import DIMENSION_CATALOG, JOIN_CATALOG, METRIC_CATALOG
from .contracts import AnalysisFilter, AnalysisPlan, AnalysisTimeRange


CHATBI_CONTEXT_KEYS = (
    "metric",
    "dimensions",
    "filters",
    "time_range",
    "comparison",
    "drill_level",
    "analysis_plan_id",
)
CHATBI_CONTEXT_SOURCE_PREFIX = "chatbi_context:"


def analysis_context(plan: AnalysisPlan) -> dict[str, Any]:
    """Return the only business context fields ChatBI is allowed to remember."""
    return {
        "metric": list(plan.metrics),
        "dimensions": list(plan.dimensions),
        "filters": [item.model_dump(mode="json") for item in plan.filters],
        "time_range": plan.time_range.model_dump(mode="json") if plan.time_range else None,
        "comparison": plan.comparison,
        "drill_level": plan.drill_level,
        "analysis_plan_id": plan.analysis_plan_id,
    }


def remember_analysis_context(
    identity: IdentityContext,
    plan: AnalysisPlan,
    *,
    engine: Engine | None = None,
) -> dict[str, Any]:
    identity.require_valid(require_session=True)
    now = datetime.now(timezone.utc)
    return admit_memory(
        identity,
        content=json.dumps(analysis_context(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        summary="ChatBI 分析上下文",
        memory_type="episodic",
        subject_type="task_episode",
        source_type="tool_verified",
        source_id=f"{CHATBI_CONTEXT_SOURCE_PREFIX}{identity.session_id}:{plan.analysis_plan_id}",
        confidence=0.99,
        importance=0.7,
        business_value=0.8,
        expires_at=now + timedelta(days=30),
        metadata={"context_schema": "chatbi_analysis_context_v1"},
        occurred_at=now,
        engine=engine,
    )


def recall_analysis_context(identity: IdentityContext, *, engine: Engine | None = None) -> dict[str, Any] | None:
    identity.require_valid(require_session=True)
    prefix = f"{CHATBI_CONTEXT_SOURCE_PREFIX}{identity.session_id}:"
    memories = retrieve_memories(
        identity,
        "",
        memory_types=("episodic",),
        limit=12,
        engine=engine,
        session_id=identity.session_id,
    )
    for item in memories:
        if item.get("source_type") != "tool_verified" or not str(item.get("source_id") or "").startswith(prefix):
            continue
        if item.get("session_id") != identity.session_id:
            continue
        try:
            payload = json.loads(str(item.get("content") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and set(payload) == set(CHATBI_CONTEXT_KEYS):
            return payload
    return None


def _registered(values: Any, catalog: dict[str, Any], *, maximum: int) -> list[str]:
    if not isinstance(values, list) or len(values) > maximum:
        return []
    result = [str(value) for value in values if str(value) in catalog]
    return result if len(result) == len(values) and len(result) == len(set(result)) else []


def _derived_datasets(metrics: list[str], dimensions: list[str]) -> list[str]:
    datasets: list[str] = []
    for metric_id in metrics:
        for dataset_id in METRIC_CATALOG[metric_id].allowed_datasets:
            if dataset_id not in datasets:
                datasets.append(dataset_id)
    for dimension_id in dimensions:
        dataset_id = DIMENSION_CATALOG[dimension_id].dataset
        if dataset_id not in datasets:
            datasets.append(dataset_id)
    return datasets


def _derived_joins(datasets: list[str], metrics: list[str], dimensions: list[str]) -> list[str]:
    if len(datasets) < 2:
        return []
    for join in JOIN_CATALOG.values():
        if (
            {join.left_dataset, join.right_dataset} == set(datasets)
            and set(metrics).issubset(join.allowed_metrics)
            and set(dimensions).issubset(join.allowed_dimensions)
        ):
            return [join.join_id]
    return []


def apply_remembered_context(plan: AnalysisPlan, remembered: dict[str, Any] | None) -> tuple[AnalysisPlan, dict[str, Any]]:
    """Fill only omitted plan facts. Explicit current-query fields always win."""
    remembered = remembered or {}
    explicit = set(plan.model_fields_set)
    updates: dict[str, Any] = {}
    restored: list[str] = []

    metrics = _registered(remembered.get("metric"), METRIC_CATALOG, maximum=8)
    dimensions = _registered(remembered.get("dimensions"), DIMENSION_CATALOG, maximum=8)
    if "metrics" not in explicit and metrics:
        updates["metrics"] = metrics
        restored.append("metric")
    if "dimensions" not in explicit and dimensions:
        updates["dimensions"] = dimensions
        restored.append("dimensions")
    if "filters" not in explicit and isinstance(remembered.get("filters"), list):
        try:
            updates["filters"] = [AnalysisFilter.model_validate(item) for item in remembered["filters"]]
            restored.append("filters")
        except (TypeError, ValueError):
            pass
    if "time_range" not in explicit and remembered.get("time_range"):
        try:
            updates["time_range"] = AnalysisTimeRange.model_validate(remembered["time_range"])
            restored.append("time_range")
        except (TypeError, ValueError):
            pass
    time_was_explicitly_cleared = "time_range" in explicit and plan.time_range is None
    if (
        "comparison" not in explicit
        and not time_was_explicitly_cleared
        and remembered.get("comparison") in {"previous_period", "yoy", "mom"}
    ):
        updates["comparison"] = remembered["comparison"]
        restored.append("comparison")
    if "drill_level" not in explicit and remembered.get("drill_level") in DIMENSION_CATALOG:
        updates["drill_level"] = remembered["drill_level"]
        restored.append("drill_level")

    merged = plan.model_copy(update=updates)
    derived: dict[str, Any] = {}
    if "datasets" not in explicit:
        derived["datasets"] = _derived_datasets(list(merged.metrics), list(merged.dimensions))
    if "group_by" not in explicit and merged.dimensions:
        non_time = [item for item in merged.dimensions if DIMENSION_CATALOG[item].data_type != "datetime"]
        derived["group_by"] = non_time or ([merged.dimensions[0]] if merged.time_range else [])
    if "time_grain" not in explicit and derived.get("group_by"):
        if any(DIMENSION_CATALOG[item].data_type == "datetime" for item in derived["group_by"]):
            derived["time_grain"] = "day"
    if "joins" not in explicit:
        datasets = list(derived.get("datasets", merged.datasets))
        derived["joins"] = _derived_joins(datasets, list(merged.metrics), list(merged.dimensions))
    if "chart_intent" not in explicit:
        group_by = list(derived.get("group_by", merged.group_by))
        derived["chart_intent"] = "line" if group_by and DIMENSION_CATALOG[group_by[0]].data_type == "datetime" else ("bar" if group_by else "table")
    merged = merged.model_copy(update=derived)
    return merged, {
        "used": bool(restored),
        "parent_analysis_plan_id": remembered.get("analysis_plan_id"),
        "restored_fields": restored,
    }
