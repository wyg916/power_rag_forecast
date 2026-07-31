from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import inspect, text

from backend.app.config import APP_VERSION, PLATFORM_NAME, project_config, project_paths
from backend.app.core.config import get_settings
from backend.app.data_access import data_status, database_engine, database_runtime_status, jsonable, records
from backend.app.observability import recent_suppressed_exceptions
from backend.app.repositories.audit_repository import write_audit_log
from backend.app.repositories.task_repository import list_recent_tasks, list_task_runs


def response(data: Any, data_source: str | None = "postgresql", message: str = "success", code: int = 0) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": jsonable(data),
        "trace_id": "api_" + uuid.uuid4().hex[:12],
        "timestamp": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "data_source": data_source,
    }


def _safe_time(value: Any) -> str:
    return str(value or "")[:19]


def _legacy_data_quality_report() -> dict[str, Any]:
    status = data_status()
    sources = status.get("sources") or []
    rows: list[dict[str, Any]] = []
    for item in sources:
        total = int(item.get("rows") or 0)
        missing = int(item.get("missing_values") or 0) if item.get("missing_values") is not None else 0
        missing_rate = round((missing / total) * 100, 4) if total else 0
        rows.append(
            {
                "source_name": item.get("name"),
                "status": item.get("status"),
                "latest_time": item.get("latest_time"),
                "start_time": item.get("start_time"),
                "rows": total,
                "missing_values": missing,
                "missing_rate": missing_rate,
                "duplicate_rate": None,
                "freshness_score": None,
                "check_pass_rate": 100 - min(missing_rate, 100),
                "message": item.get("message") or "",
                "data_source": item.get("source") or item.get("internal_file") or "",
            }
        )
    exception_rows = [row for row in rows if row["missing_rate"] > 0 or str(row.get("status")) not in {"正常", "success", "ok"}]
    return {
        "available": True,
        "summary": {
            "source_count": len(rows),
            "exception_count": len(exception_rows),
            "avg_missing_rate": round(sum(row["missing_rate"] for row in rows) / len(rows), 4) if rows else 0,
            "avg_check_pass_rate": round(sum(row["check_pass_rate"] for row in rows) / len(rows), 2) if rows else None,
        },
        "items": rows,
        "exceptions": exception_rows,
    }


def _legacy_import_export_records() -> dict[str, Any]:
    tasks = list_recent_tasks(limit=120)
    items = []
    for task in tasks:
        kind = str(task.get("kind") or task.get("task_kind") or "")
        if any(key in kind for key in ["sync", "data", "import", "export", "report"]):
            items.append(
                {
                    "record_id": task.get("task_id"),
                    "type": "导出" if "export" in kind or "report" in kind else "导入/同步",
                    "name": task.get("task_name") or kind,
                    "status": task.get("status"),
                    "rows": task.get("row_count") or "",
                    "started_at": task.get("started_at"),
                    "ended_at": task.get("ended_at"),
                    "duration_seconds": task.get("duration_seconds"),
                    "error_message": task.get("error_message") or "",
                    "data_source": "postgresql.task_runs",
                }
            )
    return {"available": True, "records": items}


QUALITY_DATASETS = (
    "raw_market",
    "raw_da_price",
    "raw_rt_price",
    "raw_actual_load",
    "raw_load",
    "raw_forecast_load_selected",
    "raw_weather",
    "model_master_table",
    "forecast_results",
)


def _quality_average(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return round(sum(values) / len(values), 2) if values else None


def _freshness_score(latest_time: Any, threshold_hours: int = 48) -> tuple[float | None, float | None]:
    if latest_time in (None, ""):
        return None, None
    stamp = pd.Timestamp(latest_time)
    now = pd.Timestamp.now(tz=stamp.tz) if stamp.tzinfo else pd.Timestamp.now()
    age_hours = max(0.0, (now - stamp).total_seconds() / 3600)
    score = max(0.0, 100 - max(0.0, age_hours - threshold_hours) * 100 / (threshold_hours * 3))
    return round(score, 2), round(age_hours, 2)


def _quality_alert(row: dict[str, Any], checked_at: str) -> dict[str, Any] | None:
    status = str(row.get("status") or "")
    if status == "ok":
        return None
    if status == "missing_table":
        alert_type, severity, message = "schema", "critical", "数据库表或视图不存在"
    elif status == "empty":
        alert_type, severity, message = "empty", "high", "对象存在但没有有效记录"
    elif row.get("is_stale"):
        alert_type, severity, message = "freshness", "high", str(row.get("stale_reason") or "数据超过刷新阈值")
    else:
        alert_type, severity, message = "quality", "medium", str(row.get("message") or "质量指标未达到阈值")
    table_name = str(row.get("table_name") or row.get("source_name") or "unknown")
    return {
        "alert_id": f"quality:{table_name}:{alert_type}",
        "severity": severity,
        "alert_type": alert_type,
        "object_name": table_name,
        "detected_at": checked_at,
        "status": "open",
        "source": "postgresql quality aggregate",
        "message": message,
        "latest_time": row.get("latest_time"),
        "stale_reason": row.get("stale_reason"),
    }


def data_quality_report() -> dict[str, Any]:
    from .dataset_query_service import dataset_quality_report

    return dataset_quality_report()


def _task_metric(task: dict[str, Any], *names: str) -> int | None:
    for container in (task, task.get("metadata") or {}, task.get("payload") or {}):
        for name in names:
            if name in container and container[name] not in (None, ""):
                try:
                    return int(container[name])
                except (TypeError, ValueError):
                    return None
    return None


def import_export_records(page: int = 1, page_size: int = 10) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 10), 50))
    task_page = list_task_runs(
        kind_keywords=("sync", "data", "import", "export", "report"),
        page=page,
        page_size=page_size,
    )
    tasks = list(task_page.get("list") or [])
    items: list[dict[str, Any]] = []
    for task in tasks:
        kind = str(task.get("kind") or task.get("task_kind") or "")
        processed_rows = _task_metric(task, "processed_rows", "row_count", "rows")
        success_rows = _task_metric(task, "success_rows", "succeeded_rows", "inserted_rows")
        failed_rows = _task_metric(task, "failed_rows", "failure_rows", "error_rows")
        items.append(
            {
                "record_id": task.get("task_id"),
                "run_id": task.get("run_id"),
                "type": "导出" if "export" in kind or "report" in kind else "导入/同步",
                "name": task.get("task_name") or kind,
                "task_kind": kind,
                "status": task.get("status"),
                "processed_rows": processed_rows,
                "success_rows": success_rows,
                "failed_rows": failed_rows,
                "created_at": task.get("created_at"),
                "started_at": task.get("started_at") or task.get("queued_at") or task.get("created_at"),
                "ended_at": task.get("ended_at") or task.get("finished_at"),
                "duration_seconds": task.get("duration_seconds"),
                "error_code": task.get("error_code") or "",
                "error_message": task.get("error_message") or "",
                "status_reason": None if processed_rows is not None else "当前任务记录未保存处理行数",
                "data_source": "postgresql.task_runs",
            }
        )
    total = int(task_page.get("total") or 0)
    task_summary = task_page.get("summary") or {}
    latest = task_page.get("latest") or {}
    return {
        "available": True,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "records": items,
        "pagination": {"page": page, "page_size": page_size, "total": total},
        "summary": {
            "total": total,
            "latest_sync_at": task_summary.get("latest_started_at"),
            "latest_sync_run_id": latest.get("run_id"),
            "latest_success_at": task_summary.get("latest_success_at"),
            "today_task_count": int(task_summary.get("today_task_count") or 0),
            "today_processed_rows": None,
        },
        "data_source": "postgresql.task_runs",
    }


def export_table_to_csv(table_name: str, search: str | None = None, max_rows: int = 5000) -> dict[str, Any]:
    del max_rows
    from .dataset_query_service import export_dataset_csv

    return export_dataset_csv(table_name, search=search)


def _mask(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "******"
    return f"{text[:3]}****{text[-4:]}"


def runtime_settings_path() -> Path:
    return project_paths().current_dir / "web_runtime_settings.json"


def _read_runtime_settings() -> dict[str, Any]:
    path = runtime_settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_runtime_settings(payload: dict[str, Any]) -> dict[str, Any]:
    path = runtime_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = _read_runtime_settings()
    current.update(payload)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def system_config_snapshot() -> dict[str, Any]:
    settings = get_settings()
    cfg = project_config()
    runtime = _read_runtime_settings()
    database_url = os.getenv("DATABASE_URL", "")
    engine = database_engine()
    database_status = database_runtime_status()
    return {
        "platform": PLATFORM_NAME,
        "version": APP_VERSION,
        "auth_required": settings.auth_required,
        "database": {
            "DATABASE_URL": _mask(database_url),
            "configured": bool(database_url),
            "primary": settings.database_primary,
            "fallback_allowed": settings.database_allow_legacy_fallback,
            "active": database_status.get("active"),
            "message": database_status.get("message"),
            "engine": engine.dialect.name if engine is not None else "unavailable",
        },
        "model_gateway": {
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", cfg.get("llm", {}).get("provider", "")),
            "LLM_BASE_URL": os.getenv("LLM_BASE_URL", ""),
            "LLM_MODEL": os.getenv("LLM_MODEL", ""),
            "LLM_API_KEY": _mask(os.getenv("LLM_API_KEY", "")),
        },
        "web": {
            "backend_host": os.getenv("WEB_BACKEND_HOST", "127.0.0.1"),
            "backend_port": os.getenv("WEB_BACKEND_PORT", "8000"),
            "frontend_port": os.getenv("WEB_FRONTEND_PORT", "5173"),
        },
        "runtime": runtime,
    }


def save_system_config(payload: dict[str, Any], user: Any = None, ip_address: str = "") -> dict[str, Any]:
    saved = _write_runtime_settings(payload)
    write_audit_log(
        action="settings.save",
        user=user,
        resource_type="settings",
        status="success",
        ip_address=ip_address,
        metadata={"keys": sorted(payload.keys())},
    )
    return {"saved": True, "runtime": saved}


def system_health_snapshot() -> dict[str, Any]:
    engine = database_engine()
    db_ok = bool(engine is not None and engine.dialect.name == "postgresql")
    database_status = database_runtime_status()
    paths = project_paths()
    return {
        "service": "ok",
        "database": "ok" if db_ok else "unavailable",
        "database_primary": database_status,
        "recent_backend_exceptions": recent_suppressed_exceptions(limit=8),
        "config_file": str(runtime_settings_path()),
        "current_output_dir": str(paths.current_dir),
        "disk_outputs_exist": paths.current_dir.exists(),
        "timestamp": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
