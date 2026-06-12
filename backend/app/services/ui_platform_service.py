from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import APP_VERSION, PLATFORM_NAME, project_config, project_paths
from backend.app.core.config import get_settings
from backend.app.data_access import data_status, database_engine, database_runtime_status, database_table_rows, jsonable, records
from backend.app.observability import recent_suppressed_exceptions
from backend.app.repositories.audit_repository import write_audit_log
from backend.app.repositories.task_repository import list_recent_tasks


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


def data_quality_report() -> dict[str, Any]:
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
                "duplicate_rate": 0,
                "freshness_score": 100 if item.get("latest_time") else 60,
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
            "avg_check_pass_rate": round(sum(row["check_pass_rate"] for row in rows) / len(rows), 2) if rows else 100,
        },
        "items": rows,
        "exceptions": exception_rows,
    }


def import_export_records() -> dict[str, Any]:
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


def export_table_to_csv(table_name: str, search: str | None = None) -> Path:
    payload = database_table_rows(table_name, search=search, limit=200, offset=0)
    rows = payload.get("records") or []
    paths = project_paths()
    export_dir = paths.current_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path


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
