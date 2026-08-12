from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text

from backend.app.ai_assistant.core.llm_client import get_local_llm_status
from backend.app.core.config import get_settings
from backend.app.core.redaction import mask_db_url, mask_secret_fields
from backend.app.core.security import CurrentUser, ROLE_PERMISSIONS
from backend.app.data_access import database_runtime_status, jsonable
from backend.app.repositories.audit_repository import list_audit_logs, write_audit_log
from backend.app.repositories.base import postgres_engine
from backend.app.repositories.settings_repository import (
    health_check_records,
    insert_api_test_log,
    insert_health_snapshot,
    latest_health_snapshots,
    list_api_configs,
    list_api_test_logs,
    list_role_permissions,
    list_runtime_config,
    runtime_config_map,
    update_api_config_status,
    upsert_api_config,
    upsert_role_permissions,
    upsert_runtime_config,
)
from backend.app.repositories.task_repository import queue_overview, task_runtime_summary
from backend.app.repositories.user_repository import (
    create_user,
    ensure_not_last_admin_demoted_or_disabled,
    get_user_by_id,
    list_users,
    normalize_role,
    set_user_active,
    update_password_hash,
    update_user,
)
from backend.app.services.rag_health_service import rag_health
from backend.app.workers.dispatcher import task_runtime_health


RUNTIME_DEFAULTS = [
    ("data_refresh_interval_minutes", 5, "integer", "runtime", "Data refresh interval"),
    ("forecast_timeout_seconds", 180, "integer", "runtime", "Forecast calculation timeout"),
    ("risk_threshold_percent", 85, "number", "runtime", "Risk threshold percent"),
    ("anomaly_warning_threshold_percent", 90, "number", "runtime", "Anomaly warning threshold percent"),
    ("email_notification_enabled", True, "boolean", "runtime", "Email notification"),
    ("sms_notification_enabled", False, "boolean", "runtime", "SMS notification"),
    ("maintenance_mode_enabled", False, "boolean", "runtime", "Maintenance mode"),
    ("auto_backup_enabled", True, "boolean", "runtime", "Automatic data backup"),
    ("password_min_length", 12, "integer", "security_policy", "Minimum password length"),
    ("login_failed_lock_count", 5, "integer", "security_policy", "Failed login lock threshold"),
    ("session_timeout_minutes", 30, "integer", "security_policy", "Session timeout"),
    ("force_periodic_password_change", True, "boolean", "security_policy", "Force periodic password change"),
    ("two_factor_enabled", False, "boolean", "security_policy", "Two factor authentication"),
    ("admin_reset_password_enabled", True, "boolean", "security_policy", "Admin password reset"),
]


def seed_settings_defaults(updated_by: str = "system") -> None:
    for key, value, value_type, category, description in RUNTIME_DEFAULTS:
        exists = any(row.get("config_key") == key for row in list_runtime_config(category))
        if not exists:
            upsert_runtime_config(key, value, value_type=value_type, category=category, description=description, updated_by=updated_by)
    for payload in default_api_configs():
        current = list_api_configs(keyword=payload["interface_name"], page_size=1)["items"]
        if not any(item.get("interface_key") == payload["interface_key"] for item in current):
            upsert_api_config(payload, updated_by=updated_by)
    for role in default_role_permissions():
        existing = {item.get("role_id") for item in list_role_permissions()}
        if role["role_id"] not in existing:
            upsert_role_permissions(role["role_id"], role["permissions"], role_name=role["role_name"], description=role["description"])


def default_api_configs() -> list[dict[str, Any]]:
    settings = get_settings()
    db_url = settings.database_url.strip()
    db_parts = urlsplit(db_url) if db_url else None
    db_host = db_parts.hostname if db_parts else ""
    db_port = db_parts.port if db_parts else None
    db_name = db_parts.path.lstrip("/") if db_parts else ""
    db_user = db_parts.username if db_parts else ""
    return [
        {
            "interface_key": "postgresql",
            "interface_name": "PostgreSQL",
            "interface_type": "database",
            "service_url": mask_db_url(db_url),
            "host": db_host,
            "port": db_port,
            "database_name": db_name,
            "username": db_user,
            "secret_ref": "DATABASE_URL",
            "status": "not_configured" if not db_url else "warning",
            "extra_json": {"source": "env", "secret_ref": "DATABASE_URL"},
        },
        {
            "interface_key": "redis",
            "interface_name": "Redis",
            "interface_type": "cache",
            "service_url": mask_db_url(settings.redis_url),
            "secret_ref": "REDIS_URL",
            "status": "warning",
            "extra_json": {"source": "env", "secret_ref": "REDIS_URL"},
        },
        {
            "interface_key": "celery",
            "interface_name": "Celery Broker",
            "interface_type": "task_queue",
            "service_url": mask_db_url(settings.celery_broker_url),
            "secret_ref": "CELERY_BROKER_URL",
            "status": "warning",
            "extra_json": {"result_backend": mask_db_url(settings.celery_result_backend), "execution_mode": settings.task_execution_mode},
        },
        {
            "interface_key": "web",
            "interface_name": "FastAPI Web",
            "interface_type": "web_service",
            "service_url": os.getenv("WEB_BACKEND_BASE_URL", "http://127.0.0.1:8000"),
            "health_path": "/api/health",
            "protocol": "HTTP",
            "environment": settings.app_env,
            "status": "warning",
        },
        {
            "interface_key": "rag",
            "interface_name": "RAG / BGE",
            "interface_type": "rag",
            "service_url": os.getenv("RAG_SERVICE_URL", "local"),
            "status": "warning",
            "extra_json": {"profile": settings.rag_profile},
        },
        {
            "interface_key": "milvus",
            "interface_name": "Milvus",
            "interface_type": "vector_database",
            "service_url": os.getenv("MILVUS_URI", ""),
            "status": "not_configured" if not os.getenv("MILVUS_URI", "") else "warning",
            "extra_json": {"collection": os.getenv("MILVUS_COLLECTION", "")},
        },
        {
            "interface_key": "llm",
            "interface_name": "LLM / Ollama / DeepSeek",
            "interface_type": "llm",
            "service_url": settings.llm_base_url,
            "secret_ref": "LLM_API_KEY",
            "status": "warning",
            "extra_json": {"provider": settings.llm_provider, "model": settings.llm_model},
        },
        {
            "interface_key": "audit",
            "interface_name": "Audit API",
            "interface_type": "audit",
            "service_url": "/api/settings/audit-logs",
            "status": "normal",
            "extra_json": {"source_table": "audit_logs"},
        },
    ]


def default_role_permissions() -> list[dict[str, Any]]:
    names = {
        "admin": "超级管理员",
        "analyst": "业务分析师",
        "developer": "开发调试员",
        "viewer": "只读用户",
        "operator": "运行操作员",
    }
    descriptions = {
        "admin": "拥有系统设置、用户权限、审计和全部业务能力。",
        "analyst": "可执行预测、报告、知识库和常规任务。",
        "developer": "可查看调试 Trace、模型和系统运行信息。",
        "viewer": "只读查看核心业务页面。",
        "operator": "可执行任务、报告和基础业务操作。",
    }
    roles = []
    for role in ["admin", "analyst", "developer", "viewer", "operator"]:
        permissions = sorted(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS.get("viewer", set())))
        roles.append({"role_id": role, "role_name": names[role], "description": descriptions[role], "permissions": permissions})
    return roles


def status_from_bool(ok: bool, *, not_configured: bool = False) -> str:
    if not_configured:
        return "not_configured"
    return "normal" if ok else "warning"


def status_label(value: str) -> str:
    return {
        "normal": "正常",
        "warning": "告警",
        "error": "异常",
        "unavailable": "不可用",
        "not_configured": "未配置",
        "fallback": "降级",
        "partial": "部分可用",
        "disabled": "停用",
    }.get(str(value or "").lower(), value or "未知")


def collect_runtime_health_rows() -> list[dict[str, Any]]:
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    db_status = database_runtime_status()
    db_ok = bool(db_status.get("active") == "postgresql")
    try:
        task_health = task_runtime_health()
    except Exception as exc:
        task_health = {"ok": False, "message": str(exc)}
    try:
        rag = rag_health()
    except Exception as exc:
        rag = {"ok": False, "status": "error", "error": str(exc)}
    try:
        llm = get_local_llm_status()
    except Exception as exc:
        llm = {"available": False, "message": str(exc)}
    rows = [
        {
            "module_key": "auth",
            "module_name": "认证服务",
            "module_type": "security",
            "status": "normal",
            "summary": "认证依赖已加载，权限校验可用",
            "latency_ms": None,
            "qps": None,
            "error_rate": 0,
            "extra_json": {"source": "fastapi_dependency"},
            "checked_at": now,
            "source": "runtime",
        },
        {
            "module_key": "postgresql",
            "module_name": "PostgreSQL 数据库",
            "module_type": "database",
            "status": status_from_bool(db_ok),
            "summary": str(db_status.get("message") or db_status.get("active") or "database status unknown"),
            "latency_ms": None,
            "qps": None,
            "error_rate": 0 if db_ok else 1,
            "extra_json": db_status,
            "checked_at": now,
            "source": "runtime",
        },
        {
            "module_key": "redis",
            "module_name": "Redis 缓存服务",
            "module_type": "cache",
            "status": status_from_bool(bool(task_health.get("redis", {}).get("ok"))),
            "summary": str(task_health.get("redis", {}).get("status") or task_health.get("message") or "redis status unknown"),
            "latency_ms": None,
            "qps": None,
            "error_rate": 0 if task_health.get("redis", {}).get("ok") else 1,
            "extra_json": task_health.get("redis") or {},
            "checked_at": now,
            "source": "runtime",
        },
        {
            "module_key": "celery",
            "module_name": "Celery 任务队列",
            "module_type": "task_queue",
            "status": status_from_bool(bool(task_health.get("celery", {}).get("ok"))),
            "summary": f"workers={task_health.get('celery', {}).get('worker_count', 0)}, pending={task_health.get('pending_task_count', 0)}, running={task_health.get('running_task_count', 0)}",
            "latency_ms": None,
            "qps": None,
            "error_rate": 0 if task_health.get("celery", {}).get("ok") else 1,
            "extra_json": task_health,
            "checked_at": now,
            "source": "runtime",
        },
        {
            "module_key": "rag",
            "module_name": "RAG / BGE 服务",
            "module_type": "rag",
            "status": str(rag.get("status") or status_from_bool(bool(rag.get("ok")))),
            "summary": "; ".join(rag.get("fallback_reasons") or []) or f"chunks={rag.get('kb_chunk_count', 0)}, embedded={rag.get('embedded_chunk_count', 0)}",
            "latency_ms": None,
            "qps": None,
            "error_rate": 0 if rag.get("ok") else 1,
            "extra_json": rag,
            "checked_at": now,
            "source": "runtime",
        },
        {
            "module_key": "llm",
            "module_name": "LLM 模型服务",
            "module_type": "llm",
            "status": status_from_bool(bool(llm.get("available") or llm.get("ok"))),
            "summary": str(llm.get("message") or llm.get("provider") or llm.get("model") or "llm status unknown"),
            "latency_ms": None,
            "qps": None,
            "error_rate": 0 if (llm.get("available") or llm.get("ok")) else 1,
            "extra_json": llm,
            "checked_at": now,
            "source": "runtime",
        },
        {
            "module_key": "milvus",
            "module_name": "Milvus 向量库",
            "module_type": "vector_database",
            "status": "not_configured" if not os.getenv("MILVUS_URI", "") else "warning",
            "summary": os.getenv("MILVUS_URI", "") or "未配置独立 Milvus 连接",
            "latency_ms": None,
            "qps": None,
            "error_rate": None,
            "extra_json": {"milvus_uri_configured": bool(os.getenv("MILVUS_URI", ""))},
            "checked_at": now,
            "source": "runtime",
        },
        {
            "module_key": "prometheus",
            "module_name": "Prometheus 监控",
            "module_type": "monitoring",
            "status": "not_configured" if not os.getenv("PROMETHEUS_URL", "") else "warning",
            "summary": os.getenv("PROMETHEUS_URL", "") or "未配置 Prometheus 探针",
            "latency_ms": None,
            "qps": None,
            "error_rate": None,
            "extra_json": {"prometheus_url_configured": bool(os.getenv("PROMETHEUS_URL", ""))},
            "checked_at": now,
            "source": "runtime",
        },
        {
            "module_key": "audit",
            "module_name": "日志服务",
            "module_type": "audit",
            "status": "normal",
            "summary": "audit_logs 表与审计查询接口可用",
            "latency_ms": None,
            "qps": None,
            "error_rate": 0,
            "extra_json": {"source_table": "audit_logs"},
            "checked_at": now,
            "source": "runtime",
        },
    ]
    for row in rows:
        try:
            insert_health_snapshot(**{key: row[key] for key in ["module_key", "module_name", "module_type", "status", "summary", "latency_ms", "qps", "error_rate", "extra_json", "source"]})
        except Exception:
            pass
    return rows


def system_status_overview(*, user: CurrentUser | None = None) -> dict[str, Any]:
    rows = collect_runtime_health_rows()
    healthy = sum(1 for row in rows if row["status"] in {"normal", "partial"})
    warnings = sum(1 for row in rows if row["status"] in {"warning", "fallback", "not_configured", "unavailable"})
    errors = sum(1 for row in rows if row["status"] == "error")
    scope = (
        {"tenant_id": user.tenant_id, "workspace_id": user.workspace_id}
        if user is not None
        else {}
    )
    users = list_users(page=1, page_size=1, **scope)
    active_users = list_users(is_active=True, page=1, page_size=1, **scope)
    health_score = round((healthy / len(rows)) * 100, 2) if rows else 0
    return {
        "online_users": active_users.get("total", 0),
        "user_total": users.get("total", 0),
        "healthy_services": healthy,
        "total_services": len(rows),
        "warning_count": warnings,
        "error_count": errors,
        "system_health_score": health_score,
        "status_source": "runtime",
        "checked_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }


def system_status_summary() -> list[dict[str, Any]]:
    return [_public_health_row(row) for row in collect_runtime_health_rows()]


def system_health_details() -> list[dict[str, Any]]:
    collect_runtime_health_rows()
    rows = latest_health_snapshots(limit=100)
    return [_public_health_row(row) for row in rows]


def _public_health_row(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "")
    return {
        "key": row.get("module_key"),
        "module_key": row.get("module_key"),
        "module_name": row.get("module_name"),
        "module_type": row.get("module_type"),
        "status": status,
        "status_label": status_label(status),
        "summary": row.get("summary") or "",
        "latency_ms": row.get("latency_ms"),
        "qps": row.get("qps"),
        "error_rate": row.get("error_rate"),
        "metric": _metric_text(row),
        "checked_at": str(row.get("checked_at") or "")[:19],
        "source": row.get("source") or "runtime",
        "extra": mask_secret_fields(row.get("extra_json") or {}),
    }


def _metric_text(row: dict[str, Any]) -> str:
    latency = row.get("latency_ms")
    qps = row.get("qps")
    error_rate = row.get("error_rate")
    latency_text = f"{latency}ms" if latency is not None else "--"
    qps_text = str(qps) if qps is not None else "--"
    error_text = f"{error_rate}%" if error_rate is not None else "--"
    return f"{latency_text} / {qps_text} / {error_text}"


def get_runtime_config_payload() -> dict[str, Any]:
    seed_settings_defaults()
    return runtime_config_map()


def update_runtime_config_payload(payload: dict[str, Any], *, user: CurrentUser, ip_address: str = "") -> dict[str, Any]:
    seed_settings_defaults(updated_by=user.username)
    values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
    existing = {row["config_key"]: row for row in list_runtime_config()}
    updated = []
    for key, value in (values or {}).items():
        current = existing.get(str(key))
        value_type = str(current.get("value_type") if current else _infer_value_type(value))
        category = str(current.get("category") if current else "runtime")
        row = upsert_runtime_config(
            str(key),
            value,
            value_type=value_type,
            category=category,
            description=str(current.get("description") if current else ""),
            is_sensitive=bool(current.get("is_sensitive") if current else False),
            is_enabled=bool(current.get("is_enabled", True) if current else True),
            updated_by=user.username,
        )
        updated.append(row)
    write_audit_log(
        action="settings.runtime_config.update",
        user=user,
        resource_type="settings",
        status="success",
        ip_address=ip_address,
        metadata={"keys": sorted(str(key) for key in (values or {}).keys())},
    )
    return {"updated": updated, **runtime_config_map()}


def _infer_value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (dict, list)):
        return "json"
    return "string"


def health_records(limit: int = 100) -> list[dict[str, Any]]:
    collect_runtime_health_rows()
    return [_public_health_row(row) for row in health_check_records(limit=limit)]


def task_queue_snapshot() -> dict[str, Any]:
    try:
        runtime = task_runtime_summary()
        queues = queue_overview()
    except Exception:
        runtime = {}
        queues = []
    status_counts = runtime.get("status_counts") or {}
    return {
        "total_tasks": sum(int(value or 0) for value in status_counts.values()) if isinstance(status_counts, dict) else 0,
        "pending_count": int(runtime.get("pending_task_count") or 0),
        "running_count": int(runtime.get("running_task_count") or 0),
        "failed_count": int(runtime.get("failed_task_count") or 0),
        "queues": queues,
        "source": "task_runs",
        "checked_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }


def users_overview(*, user: CurrentUser | None = None) -> dict[str, Any]:
    scope = (
        {"tenant_id": user.tenant_id, "workspace_id": user.workspace_id}
        if user is not None
        else {}
    )
    total = list_users(page=1, page_size=1, **scope).get("total", 0)
    active = list_users(is_active=True, page=1, page_size=1, **scope).get("total", 0)
    disabled = max(0, int(total or 0) - int(active or 0))
    roles = role_permissions_payload()["roles"]
    audit = list_audit_logs(limit=200, **scope)
    abnormal = sum(1 for row in audit if row.get("status") == "failed" or row.get("action") in {"auth.login_failed", "auth.login.failed"})
    return {
        "user_total": total,
        "total_users": total,
        "online_users": active,
        "role_total": len(roles),
        "role_count": len(roles),
        "abnormal_login_count": abnormal,
        "abnormal_logins": abnormal,
        "disabled_users": disabled,
        "locked_users": 0,
        "source": "users/audit_logs",
    }


def role_permissions_payload() -> dict[str, Any]:
    seed_settings_defaults()
    rows = list_role_permissions()
    if not rows:
        rows = default_role_permissions()
    permissions = ["view", "execute", "configure", "admin", "audit"]
    matrix = []
    for row in rows:
        values = set(row.get("permissions") or [])
        is_admin = "*" in values
        matrix.append(
            {
                "role_id": row.get("role_id"),
                "role_name": row.get("role_name") or row.get("role_id"),
                "permissions": sorted(values),
                "view": is_admin or any(item.endswith(":read") for item in values),
                "execute": is_admin or any(item.endswith(":run") or item.endswith(":generate") for item in values),
                "configure": is_admin or any(item.endswith(":write") or item == "settings:write" for item in values),
                "admin": is_admin,
                "audit": is_admin or "audit:read" in values,
            }
        )
    return {"roles": rows, "permissions": permissions, "matrix": matrix}


def update_role_permissions_payload(payload: dict[str, Any], *, user: CurrentUser, ip_address: str = "") -> dict[str, Any]:
    roles = payload.get("roles") or []
    updated = []
    for item in roles:
        role_id = str(item.get("role_id") or item.get("name") or "")
        if role_id == "admin" and "*" not in set(item.get("permissions") or []):
            raise ValueError("admin role must keep wildcard permission")
        updated.append(
            upsert_role_permissions(
                role_id,
                list(item.get("permissions") or []),
                role_name=str(item.get("role_name") or item.get("label") or role_id),
                description=str(item.get("description") or ""),
            )
        )
    write_audit_log(
        action="settings.role_permissions.update",
        user=user,
        resource_type="roles",
        status="success",
        ip_address=ip_address,
        metadata={"roles": [item.get("role_id") for item in updated]},
    )
    return role_permissions_payload()


def security_policy_payload() -> dict[str, Any]:
    seed_settings_defaults()
    rows = list_runtime_config("security_policy")
    return {"items": rows, "values": {row["config_key"]: row["config_value"] for row in rows}, "source": "system_runtime_config"}


def update_security_policy_payload(payload: dict[str, Any], *, user: CurrentUser, ip_address: str = "") -> dict[str, Any]:
    values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
    existing = {row["config_key"]: row for row in list_runtime_config("security_policy")}
    for key, value in (values or {}).items():
        current = existing.get(str(key))
        upsert_runtime_config(
            str(key),
            value,
            value_type=str(current.get("value_type") if current else _infer_value_type(value)),
            category="security_policy",
            description=str(current.get("description") if current else ""),
            is_sensitive=False,
            is_enabled=True,
            updated_by=user.username,
        )
    write_audit_log(
        action="settings.security_policy.update",
        user=user,
        resource_type="security_policy",
        status="success",
        ip_address=ip_address,
        metadata={"keys": sorted(str(key) for key in (values or {}).keys())},
    )
    return security_policy_payload()


def settings_audit_logs(
    limit: int = 100,
    action: str | None = None,
    *,
    user: CurrentUser | None = None,
) -> dict[str, Any]:
    scope = (
        {"tenant_id": user.tenant_id, "workspace_id": user.workspace_id}
        if user is not None
        else {}
    )
    logs = list_audit_logs(limit=limit, action=action, **scope)
    return {"items": logs, "total": len(logs), "source": "audit_logs"}


def interface_overview() -> dict[str, Any]:
    seed_settings_defaults()
    payload = list_api_configs(page_size=500)
    items = payload["items"]
    total = len(items)
    normal = sum(1 for item in items if item.get("status") == "normal")
    abnormal = sum(1 for item in items if item.get("status") in {"error", "unavailable"})
    warning = sum(1 for item in items if item.get("status") in {"warning", "not_configured", "fallback"})
    latencies = [float(item.get("last_latency_ms")) for item in items if item.get("last_latency_ms") is not None]
    return {
        "interface_total": total,
        "total_interfaces": total,
        "normal_count": normal,
        "normal_interfaces": normal,
        "abnormal_count": abnormal,
        "error_interfaces": abnormal,
        "warning_count": warning,
        "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "last_checked_at": max([str(item.get("last_checked_at") or "") for item in items] or [""]),
        "source": "system_api_configs",
    }


def interface_configs(keyword: str = "", interface_type: str = "", status: str = "", page: int = 1, page_size: int = 100) -> dict[str, Any]:
    seed_settings_defaults()
    payload = list_api_configs(keyword=keyword, interface_type=interface_type, status=status, page=page, page_size=page_size)
    payload["items"] = [_public_interface_config(item) for item in payload.get("items", [])]
    return payload


def _public_interface_config(item: dict[str, Any]) -> dict[str, Any]:
    fields = [
        {"label": "服务地址", "value": item.get("service_url") or "--"},
        {"label": "主机地址", "value": item.get("host") or "--"},
        {"label": "端口", "value": item.get("port") or "--"},
        {"label": "数据库", "value": item.get("database_name") or "--"},
        {"label": "用户名", "value": item.get("username") or "--"},
        {"label": "密钥", "value": "******" if item.get("secret_ref") or item.get("password_encrypted") or item.get("api_key_encrypted") else "--"},
    ]
    return {
        **item,
        "display_fields": [field for field in fields if field["value"] not in {None, ""}],
        "status_label": status_label(str(item.get("status") or "")),
        "masked_secrets": {"secret_ref": item.get("secret_ref") or "", "password": item.get("password_encrypted") or "", "api_key": item.get("api_key_encrypted") or ""},
    }


def update_interface_config(interface_id: str, payload: dict[str, Any], *, user: CurrentUser, ip_address: str = "") -> dict[str, Any]:
    current = None
    for item in list_api_configs(page_size=500)["items"]:
        if str(item.get("id")) == str(interface_id) or str(item.get("interface_key")) == str(interface_id):
            current = item
            break
    if not current:
        raise ValueError("interface config not found")
    merged = {**current, **payload}
    if not payload.get("password_encrypted"):
        merged["password_encrypted"] = current.get("password_encrypted")
    if not payload.get("api_key_encrypted"):
        merged["api_key_encrypted"] = current.get("api_key_encrypted")
    saved = upsert_api_config(merged, updated_by=user.username)
    write_audit_log(
        action="settings.interface.update",
        user=user,
        resource_type="system_api_config",
        resource_id=str(saved.get("interface_key") or interface_id),
        status="success",
        ip_address=ip_address,
        metadata={"interface_key": saved.get("interface_key"), "changed_keys": sorted(payload.keys())},
    )
    return _public_interface_config(saved)


def test_interface(interface_id: str, *, user: CurrentUser, ip_address: str = "") -> dict[str, Any]:
    config = None
    for item in list_api_configs(page_size=500)["items"]:
        if str(item.get("id")) == str(interface_id) or str(item.get("interface_key")) == str(interface_id):
            config = item
            break
    if not config:
        raise ValueError("interface config not found")
    result = _run_interface_probe(config)
    insert_api_test_log(
        interface_key=str(config.get("interface_key")),
        interface_name=str(config.get("interface_name")),
        test_result="success" if result["ok"] else "failed",
        latency_ms=result.get("latency_ms"),
        error_message=result.get("error_message") or "",
        tested_by=user.username,
        response_summary=result.get("summary") or "",
        extra_json=result.get("extra") or {},
    )
    update_api_config_status(
        str(config.get("interface_key")),
        status="normal" if result["ok"] else result.get("status", "error"),
        latency_ms=result.get("latency_ms"),
        success_rate=100 if result["ok"] else 0,
    )
    write_audit_log(
        action="settings.interface.test",
        user=user,
        resource_type="system_api_config",
        resource_id=str(config.get("interface_key")),
        status="success" if result["ok"] else "failed",
        ip_address=ip_address,
        metadata={"interface_key": config.get("interface_key"), "ok": result["ok"], "summary": result.get("summary")},
    )
    return {**result, "interface_key": config.get("interface_key"), "interface_name": config.get("interface_name")}


def test_all_interfaces(*, user: CurrentUser, ip_address: str = "") -> dict[str, Any]:
    seed_settings_defaults(updated_by=user.username)
    items = list_api_configs(page_size=500)["items"]
    results = []
    for item in items:
        results.append(test_interface(str(item.get("interface_key")), user=user, ip_address=ip_address))
    return {
        "items": results,
        "success_count": sum(1 for item in results if item.get("ok")),
        "failed_count": sum(1 for item in results if not item.get("ok")),
        "tested_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }


def _run_interface_probe(config: dict[str, Any]) -> dict[str, Any]:
    key = str(config.get("interface_key") or "")
    start = time.perf_counter()
    try:
        if key == "postgresql":
            engine = postgres_engine()
            if engine is None:
                return _probe_result(start, False, "PostgreSQL is not available", status="unavailable")
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return _probe_result(start, True, "SELECT 1 succeeded")
        if key == "redis":
            import redis

            client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.8, socket_timeout=0.8)
            client.ping()
            return _probe_result(start, True, "Redis PING succeeded")
        if key == "celery":
            health = task_runtime_health()
            ok = bool(health.get("celery", {}).get("ok"))
            return _probe_result(start, ok, health.get("message") or "Celery inspected", status="warning" if not ok else "normal", extra=health)
        if key == "web":
            return _probe_result(start, True, "FastAPI process is serving settings endpoint")
        if key == "rag":
            health = rag_health()
            ok = bool(health.get("ok"))
            status = "fallback" if health.get("fallback_enabled") else "warning"
            return _probe_result(start, ok, "; ".join(health.get("fallback_reasons") or []) or "RAG health checked", status=status if not ok else "normal", extra=health)
        if key == "milvus":
            uri = os.getenv("MILVUS_URI", "")
            if not uri:
                return _probe_result(start, False, "MILVUS_URI is not configured", status="not_configured")
            return _probe_result(start, False, "Milvus standalone probe is not implemented", status="warning", extra={"milvus_uri_configured": True})
        if key == "llm":
            status = get_local_llm_status()
            ok = bool(status.get("available") or status.get("ok"))
            return _probe_result(start, ok, status.get("message") or status.get("model") or "LLM checked", status="warning" if not ok else "normal", extra=status)
        if key == "audit":
            list_audit_logs(limit=1)
            return _probe_result(start, True, "Audit query succeeded")
        return _probe_result(start, False, f"Unsupported interface probe: {key}", status="not_configured")
    except Exception as exc:
        return _probe_result(start, False, str(exc)[:500], status="error")


def _probe_result(start: float, ok: bool, summary: str, *, status: str = "error", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "status": "normal" if ok else status,
        "summary": summary,
        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        "error_message": "" if ok else summary,
        "extra": mask_secret_fields(extra or {}),
    }


def interfaces_payload(keyword: str = "", interface_type: str = "", status: str = "", page: int = 1, page_size: int = 100) -> dict[str, Any]:
    return interface_configs(keyword=keyword, interface_type=interface_type, status=status, page=page, page_size=page_size)


def interface_test_logs(interface_name: str = "", result: str = "", limit: int = 100) -> dict[str, Any]:
    items = list_api_test_logs(interface_name=interface_name, result=result, limit=limit)
    return {"items": jsonable(items), "total": len(items), "source": "system_api_test_logs"}
