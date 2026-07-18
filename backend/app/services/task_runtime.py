from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


TASK_STATUSES = {"pending", "queued", "running", "success", "failed", "cancelled", "timeout", "retrying", "cancel_requested"}
TERMINAL_STATUSES = {"success", "failed", "cancelled", "timeout"}
ACTIVE_STATUSES = {"pending", "queued", "running", "retrying", "cancel_requested"}


@dataclass(frozen=True)
class TaskRuntimePolicy:
    timeout_seconds: int
    max_retries: int
    queue_name: str
    dedupe_window_seconds: int = 1800


DEFAULT_POLICY = TaskRuntimePolicy(timeout_seconds=900, max_retries=1, queue_name="default", dedupe_window_seconds=900)


TASK_POLICIES: dict[str, TaskRuntimePolicy] = {
    "knowledge_import": TaskRuntimePolicy(timeout_seconds=1800, max_retries=2, queue_name="rag", dedupe_window_seconds=1800),
    "embedding_refresh": TaskRuntimePolicy(timeout_seconds=3600, max_retries=2, queue_name="embedding", dedupe_window_seconds=3600),
    "report_generate": TaskRuntimePolicy(timeout_seconds=600, max_retries=2, queue_name="report", dedupe_window_seconds=1200),
    "report_only": TaskRuntimePolicy(timeout_seconds=600, max_retries=2, queue_name="report", dedupe_window_seconds=1200),
    "sync_core_data": TaskRuntimePolicy(timeout_seconds=1800, max_retries=3, queue_name="data_sync", dedupe_window_seconds=1800),
    "data_sync": TaskRuntimePolicy(timeout_seconds=1800, max_retries=3, queue_name="data_sync", dedupe_window_seconds=1800),
    "refresh_data": TaskRuntimePolicy(timeout_seconds=1800, max_retries=3, queue_name="data_sync", dedupe_window_seconds=1800),
    "today_analysis": TaskRuntimePolicy(timeout_seconds=1800, max_retries=2, queue_name="forecast", dedupe_window_seconds=1800),
    "fast_forecast": TaskRuntimePolicy(timeout_seconds=1800, max_retries=2, queue_name="forecast", dedupe_window_seconds=1800),
    "forecast_run": TaskRuntimePolicy(timeout_seconds=1800, max_retries=2, queue_name="forecast", dedupe_window_seconds=1800),
    "retrain_model": TaskRuntimePolicy(timeout_seconds=3600, max_retries=1, queue_name="forecast", dedupe_window_seconds=3600),
    "model_auto_optimize": TaskRuntimePolicy(timeout_seconds=3600, max_retries=1, queue_name="forecast", dedupe_window_seconds=3600),
    "health_check": TaskRuntimePolicy(timeout_seconds=300, max_retries=1, queue_name="default", dedupe_window_seconds=300),
    "data_clean": TaskRuntimePolicy(timeout_seconds=1800, max_retries=3, queue_name="data_clean", dedupe_window_seconds=1800),
    "price_predict": TaskRuntimePolicy(timeout_seconds=1800, max_retries=2, queue_name="price_predict", dedupe_window_seconds=900),
    "load_predict": TaskRuntimePolicy(timeout_seconds=1800, max_retries=2, queue_name="load_predict", dedupe_window_seconds=900),
    "strategy_gen": TaskRuntimePolicy(timeout_seconds=1200, max_retries=2, queue_name="strategy_gen", dedupe_window_seconds=900),
    "report_daily": TaskRuntimePolicy(timeout_seconds=900, max_retries=2, queue_name="report_daily", dedupe_window_seconds=1200),
    "monitor_rt": TaskRuntimePolicy(timeout_seconds=600, max_retries=3, queue_name="monitor_rt", dedupe_window_seconds=300),
    "model_train": TaskRuntimePolicy(timeout_seconds=3600, max_retries=1, queue_name="model_train", dedupe_window_seconds=3600),
}


TASK_KIND_ALIASES = {
    "forecast_run": "fast_forecast",
}


def normalize_task_kind(kind: str) -> str:
    value = str(kind or "").strip()
    return TASK_KIND_ALIASES.get(value, value)


def normalize_status(status: str | None) -> str:
    value = str(status or "pending").strip().lower()
    if value in {"ok", "done", "completed"}:
        return "success"
    if value in {"error", "exception"}:
        return "failed"
    if value == "canceled":
        return "cancelled"
    if value in {"cancelling", "cancel_requested"}:
        return "cancel_requested"
    return value if value in TASK_STATUSES else value or "pending"


def task_policy(kind: str) -> TaskRuntimePolicy:
    return TASK_POLICIES.get(normalize_task_kind(kind), DEFAULT_POLICY)


def queue_for_kind(kind: str) -> str:
    return task_policy(kind).queue_name


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def canonical_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    ignored = {
        "created_by",
        "retry_of",
        "retry_count",
        "parent_task_id",
        "original_task_id",
        "force_new",
        "dedupe_window_seconds",
        "idempotency_key",
    }
    return {key: value for key, value in sorted((payload or {}).items()) if key not in ignored}


def payload_hash(payload: dict[str, Any] | None) -> str:
    raw = json.dumps(canonical_payload(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def business_key_for_payload(kind: str, payload: dict[str, Any] | None) -> str:
    data = payload or {}
    normalized = normalize_task_kind(kind)
    if normalized == "knowledge_import":
        return str(data.get("path") or data.get("root") or data.get("source_path") or data.get("limit_files") or "local_knowledge")
    if normalized == "embedding_refresh":
        return str(data.get("scope") or data.get("doc_id") or data.get("source") or "all")
    if normalized in {"report_generate", "report_only", "report_daily"}:
        return str(data.get("report_id") or data.get("run_id") or data.get("report_type") or "latest")
    if normalized in {"sync_core_data", "refresh_data", "data_sync"}:
        return ":".join(str(data.get(key) or "") for key in ("source", "start", "end", "date", "market")) or "default"
    if normalized in {"today_analysis", "fast_forecast", "forecast_run", "retrain_model", "model_auto_optimize"}:
        return ":".join(str(data.get(key) or "") for key in ("model_version", "start", "end", "date", "market", "mode")) or "default"
    return "default"


def idempotency_key_for(kind: str, payload: dict[str, Any] | None) -> tuple[str, str]:
    data = payload or {}
    hash_value = payload_hash(data)
    explicit = str(data.get("idempotency_key") or "").strip()
    if explicit:
        return explicit, hash_value
    normalized = normalize_task_kind(kind)
    business_key = business_key_for_payload(normalized, data)
    return f"{normalized}:{business_key}:{hash_value[:16]}", hash_value


def now_iso() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def timeout_at(started_at: datetime, timeout_seconds: int) -> datetime:
    return started_at + timedelta(seconds=max(1, int(timeout_seconds or DEFAULT_POLICY.timeout_seconds)))
