from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text

from backend.app.core.redaction import mask_secret_fields

from .base import dumps_json, loads_json, mapping_dict, mapping_list, security_postgres_engine as _security_postgres_engine

# Compatibility seam; callers still receive the dedicated security engine.
postgres_engine = _security_postgres_engine


def security_postgres_engine():
    return postgres_engine()


_RUNTIME_MEMORY: dict[str, dict[str, Any]] = {}
_HEALTH_MEMORY: list[dict[str, Any]] = []
_API_CONFIG_MEMORY: dict[str, dict[str, Any]] = {}
_API_TEST_MEMORY: list[dict[str, Any]] = []


def clear_memory_settings() -> None:
    _RUNTIME_MEMORY.clear()
    _HEALTH_MEMORY.clear()
    _API_CONFIG_MEMORY.clear()
    _API_TEST_MEMORY.clear()


def _now() -> str:
    return datetime.utcnow().isoformat(sep=" ", timespec="seconds")


def _parse_value(value: Any, value_type: str = "string") -> Any:
    if value is None:
        return None
    kind = str(value_type or "string").lower()
    if kind == "boolean":
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
    if kind == "integer":
        try:
            return int(value)
        except Exception:
            return 0
    if kind == "number":
        try:
            return float(value)
        except Exception:
            return 0
    if kind == "json":
        return loads_json(value, default={})
    return str(value)


def _serialize_value(value: Any, value_type: str = "string") -> str:
    if str(value_type or "").lower() == "json":
        return dumps_json(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def _runtime_row(row: dict[str, Any]) -> dict[str, Any]:
    value = _parse_value(row.get("config_value"), str(row.get("value_type") or "string"))
    public_value = "******" if row.get("is_sensitive") and value not in {None, ""} else value
    return {
        "id": row.get("id"),
        "config_key": row.get("config_key"),
        "config_value": public_value,
        "raw_value": value,
        "value_type": row.get("value_type") or "string",
        "category": row.get("category") or "runtime",
        "description": row.get("description") or "",
        "is_sensitive": bool(row.get("is_sensitive")),
        "is_enabled": bool(row.get("is_enabled", True)),
        "updated_by": row.get("updated_by") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def upsert_runtime_config(
    config_key: str,
    config_value: Any,
    *,
    value_type: str = "string",
    category: str = "runtime",
    description: str = "",
    is_sensitive: bool = False,
    is_enabled: bool = True,
    updated_by: str = "",
) -> dict[str, Any]:
    key = str(config_key or "").strip()
    if not key:
        raise ValueError("config_key is required")
    value = _serialize_value(config_value, value_type)
    engine = security_postgres_engine()
    if engine is None:
        row = {
            "id": len(_RUNTIME_MEMORY) + 1,
            "config_key": key,
            "config_value": value,
            "value_type": value_type,
            "category": category,
            "description": description,
            "is_sensitive": is_sensitive,
            "is_enabled": is_enabled,
            "updated_by": updated_by,
            "created_at": _RUNTIME_MEMORY.get(key, {}).get("created_at") or _now(),
            "updated_at": _now(),
        }
        _RUNTIME_MEMORY[key] = row
        return _runtime_row(row)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO system_runtime_config (
                    config_key, config_value, value_type, category, description,
                    is_sensitive, is_enabled, updated_by, updated_at
                )
                VALUES (
                    :config_key, :config_value, :value_type, :category, :description,
                    :is_sensitive, :is_enabled, :updated_by, CURRENT_TIMESTAMP
                )
                ON CONFLICT (config_key) DO UPDATE SET
                    config_value = EXCLUDED.config_value,
                    value_type = EXCLUDED.value_type,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    is_sensitive = EXCLUDED.is_sensitive,
                    is_enabled = EXCLUDED.is_enabled,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """
            ),
            {
                "config_key": key,
                "config_value": value,
                "value_type": value_type,
                "category": category,
                "description": description,
                "is_sensitive": bool(is_sensitive),
                "is_enabled": bool(is_enabled),
                "updated_by": updated_by,
            },
        ).mappings().first()
    return _runtime_row(mapping_dict(row))


def list_runtime_config(category: str | None = None) -> list[dict[str, Any]]:
    engine = security_postgres_engine()
    if engine is None:
        rows = list(_RUNTIME_MEMORY.values())
        if category:
            rows = [row for row in rows if row.get("category") == category]
        return [_runtime_row(row) for row in sorted(rows, key=lambda item: str(item.get("config_key")))]
    params: dict[str, Any] = {}
    where = ""
    if category:
        where = "WHERE category = :category"
        params["category"] = category
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM system_runtime_config
                {where}
                ORDER BY category, config_key
                """
            ),
            params,
        ).mappings().all()
    return [_runtime_row(row) for row in mapping_list(rows)]


def runtime_config_map() -> dict[str, Any]:
    rows = list_runtime_config()
    values: dict[str, Any] = {}
    categories: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("config_key") or "")
        value = row.get("config_value")
        values[key] = value
        categories.setdefault(str(row.get("category") or "runtime"), {})[key] = value
    return {"items": rows, "values": values, "categories": categories}


def insert_health_snapshot(
    *,
    module_key: str,
    module_name: str,
    module_type: str,
    status: str,
    summary: str = "",
    latency_ms: float | None = None,
    qps: float | None = None,
    error_rate: float | None = None,
    extra_json: dict[str, Any] | None = None,
    source: str = "runtime",
) -> dict[str, Any]:
    row = {
        "module_key": module_key,
        "module_name": module_name,
        "module_type": module_type,
        "status": status,
        "summary": summary,
        "latency_ms": latency_ms,
        "qps": qps,
        "error_rate": error_rate,
        "extra_json": mask_secret_fields(extra_json or {}),
        "checked_at": _now(),
        "source": source,
    }
    engine = security_postgres_engine()
    if engine is None:
        row["id"] = len(_HEALTH_MEMORY) + 1
        _HEALTH_MEMORY.append(row)
        return row
    with engine.begin() as conn:
        inserted = conn.execute(
            text(
                """
                INSERT INTO system_health_snapshots (
                    module_key, module_name, module_type, status, summary,
                    latency_ms, qps, error_rate, extra_json, source
                )
                VALUES (
                    :module_key, :module_name, :module_type, :status, :summary,
                    :latency_ms, :qps, :error_rate, CAST(:extra_json AS jsonb), :source
                )
                RETURNING *
                """
            ),
            {**row, "extra_json": dumps_json(row["extra_json"])},
        ).mappings().first()
    return mapping_dict(inserted)


def latest_health_snapshots(limit: int = 50) -> list[dict[str, Any]]:
    engine = security_postgres_engine()
    if engine is None:
        return list(reversed(_HEALTH_MEMORY))[: max(1, min(int(limit or 50), 500))]
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT ON (module_key) *
                FROM system_health_snapshots
                ORDER BY module_key, checked_at DESC, id DESC
                """
            )
        ).mappings().all()
    values = mapping_list(rows)
    values.sort(key=lambda item: str(item.get("module_key") or ""))
    return values[: max(1, min(int(limit or 50), 500))]


def health_check_records(limit: int = 100) -> list[dict[str, Any]]:
    engine = security_postgres_engine()
    limit_value = max(1, min(int(limit or 100), 500))
    if engine is None:
        return list(reversed(_HEALTH_MEMORY))[:limit_value]
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM system_health_snapshots
                ORDER BY checked_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit_value},
        ).mappings().all()
    return mapping_list(rows)


def _api_config_row(row: dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    value["password_encrypted"] = "******" if value.get("password_encrypted") else ""
    value["api_key_encrypted"] = "******" if value.get("api_key_encrypted") else ""
    value["extra_json"] = mask_secret_fields(loads_json(value.get("extra_json"), default={}))
    return value


def upsert_api_config(config: dict[str, Any], *, updated_by: str = "") -> dict[str, Any]:
    key = str(config.get("interface_key") or "").strip()
    if not key:
        raise ValueError("interface_key is required")
    extra = mask_secret_fields(config.get("extra_json") or {})
    engine = security_postgres_engine()
    payload = {
        "interface_key": key,
        "interface_name": str(config.get("interface_name") or key),
        "interface_type": str(config.get("interface_type") or "service"),
        "service_url": str(config.get("service_url") or ""),
        "host": str(config.get("host") or "") or None,
        "port": config.get("port"),
        "database_name": str(config.get("database_name") or "") or None,
        "username": str(config.get("username") or "") or None,
        "password_encrypted": str(config.get("password_encrypted") or "") or None,
        "api_key_encrypted": str(config.get("api_key_encrypted") or "") or None,
        "secret_ref": str(config.get("secret_ref") or "") or None,
        "health_path": str(config.get("health_path") or "") or None,
        "protocol": str(config.get("protocol") or "") or None,
        "environment": str(config.get("environment") or "") or None,
        "timeout_seconds": int(config.get("timeout_seconds") or 5),
        "is_enabled": bool(config.get("is_enabled", True)),
        "status": str(config.get("status") or "not_configured"),
        "last_latency_ms": config.get("last_latency_ms"),
        "success_rate": config.get("success_rate"),
        "last_checked_at": config.get("last_checked_at"),
        "extra_json": extra,
        "updated_by": updated_by,
    }
    if engine is None:
        row = {**payload, "id": _API_CONFIG_MEMORY.get(key, {}).get("id") or len(_API_CONFIG_MEMORY) + 1, "created_at": _now(), "updated_at": _now()}
        _API_CONFIG_MEMORY[key] = row
        return _api_config_row(row)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO system_api_configs (
                    interface_key, interface_name, interface_type, service_url, host, port,
                    database_name, username, password_encrypted, api_key_encrypted, secret_ref,
                    health_path, protocol, environment, timeout_seconds, is_enabled, status,
                    last_latency_ms, success_rate, last_checked_at, extra_json, updated_by, updated_at
                )
                VALUES (
                    :interface_key, :interface_name, :interface_type, :service_url, :host, :port,
                    :database_name, :username, :password_encrypted, :api_key_encrypted, :secret_ref,
                    :health_path, :protocol, :environment, :timeout_seconds, :is_enabled, :status,
                    :last_latency_ms, :success_rate, :last_checked_at, CAST(:extra_json AS jsonb), :updated_by, CURRENT_TIMESTAMP
                )
                ON CONFLICT (interface_key) DO UPDATE SET
                    interface_name = EXCLUDED.interface_name,
                    interface_type = EXCLUDED.interface_type,
                    service_url = EXCLUDED.service_url,
                    host = EXCLUDED.host,
                    port = EXCLUDED.port,
                    database_name = EXCLUDED.database_name,
                    username = EXCLUDED.username,
                    password_encrypted = COALESCE(EXCLUDED.password_encrypted, system_api_configs.password_encrypted),
                    api_key_encrypted = COALESCE(EXCLUDED.api_key_encrypted, system_api_configs.api_key_encrypted),
                    secret_ref = EXCLUDED.secret_ref,
                    health_path = EXCLUDED.health_path,
                    protocol = EXCLUDED.protocol,
                    environment = EXCLUDED.environment,
                    timeout_seconds = EXCLUDED.timeout_seconds,
                    is_enabled = EXCLUDED.is_enabled,
                    status = EXCLUDED.status,
                    last_latency_ms = EXCLUDED.last_latency_ms,
                    success_rate = EXCLUDED.success_rate,
                    last_checked_at = EXCLUDED.last_checked_at,
                    extra_json = EXCLUDED.extra_json,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """
            ),
            {**payload, "extra_json": dumps_json(extra)},
        ).mappings().first()
    return _api_config_row(mapping_dict(row))


def list_api_configs(keyword: str = "", interface_type: str = "", status: str = "", *, page: int = 1, page_size: int = 100) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 100), 500))
    engine = security_postgres_engine()
    if engine is None:
        rows = [_api_config_row(row) for row in _API_CONFIG_MEMORY.values()]
        rows = _filter_api_config_rows(rows, keyword=keyword, interface_type=interface_type, status=status)
        start = (page - 1) * page_size
        return {"items": rows[start : start + page_size], "total": len(rows), "page": page, "page_size": page_size}
    where = []
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    if keyword:
        where.append("(interface_name ILIKE :keyword OR interface_type ILIKE :keyword OR service_url ILIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if interface_type:
        where.append("interface_type = :interface_type")
        params["interface_type"] = interface_type
    if status:
        where.append("status = :status")
        params["status"] = status
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM system_api_configs {where_sql}"), params).scalar_one()
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM system_api_configs
                {where_sql}
                ORDER BY interface_type, interface_name
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).mappings().all()
    return {"items": [_api_config_row(row) for row in mapping_list(rows)], "total": int(total or 0), "page": page, "page_size": page_size}


def _filter_api_config_rows(rows: list[dict[str, Any]], *, keyword: str = "", interface_type: str = "", status: str = "") -> list[dict[str, Any]]:
    values = rows
    if keyword:
        text_value = keyword.lower()
        values = [
            row
            for row in values
            if text_value in " ".join(str(row.get(key) or "") for key in ["interface_name", "interface_type", "service_url"]).lower()
        ]
    if interface_type:
        values = [row for row in values if str(row.get("interface_type") or "") == interface_type]
    if status:
        values = [row for row in values if str(row.get("status") or "") == status]
    return values


def get_api_config(interface_key_or_id: str) -> dict[str, Any] | None:
    value = str(interface_key_or_id or "").strip()
    if not value:
        return None
    engine = security_postgres_engine()
    if engine is None:
        for row in _API_CONFIG_MEMORY.values():
            if str(row.get("interface_key")) == value or str(row.get("id")) == value:
                return _api_config_row(row)
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM system_api_configs
                WHERE interface_key = :value OR CAST(id AS TEXT) = :value
                LIMIT 1
                """
            ),
            {"value": value},
        ).mappings().first()
    return _api_config_row(mapping_dict(row)) if row else None


def update_api_config_status(interface_key: str, *, status: str, latency_ms: float | None, success_rate: float | None = None) -> None:
    engine = security_postgres_engine()
    now = _now()
    if engine is None:
        row = _API_CONFIG_MEMORY.get(interface_key)
        if row:
            row.update({"status": status, "last_latency_ms": latency_ms, "success_rate": success_rate, "last_checked_at": now, "updated_at": now})
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE system_api_configs
                SET status = :status,
                    last_latency_ms = :latency_ms,
                    success_rate = COALESCE(:success_rate, success_rate),
                    last_checked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE interface_key = :interface_key
                """
            ),
            {"interface_key": interface_key, "status": status, "latency_ms": latency_ms, "success_rate": success_rate},
        )


def insert_api_test_log(
    *,
    interface_key: str,
    interface_name: str,
    test_result: str,
    latency_ms: float | None = None,
    error_message: str = "",
    tested_by: str = "",
    response_summary: str = "",
    extra_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = get_api_config(interface_key)
    row = {
        "interface_id": config.get("id") if config else None,
        "interface_key": interface_key,
        "interface_name": interface_name,
        "test_result": test_result,
        "latency_ms": latency_ms,
        "error_message": error_message,
        "tested_by": tested_by,
        "tested_at": _now(),
        "response_summary": response_summary,
        "extra_json": mask_secret_fields(extra_json or {}),
    }
    engine = security_postgres_engine()
    if engine is None:
        row["id"] = len(_API_TEST_MEMORY) + 1
        _API_TEST_MEMORY.append(row)
        return row
    with engine.begin() as conn:
        inserted = conn.execute(
            text(
                """
                INSERT INTO system_api_test_logs (
                    interface_id, interface_key, interface_name, test_result,
                    latency_ms, error_message, tested_by, response_summary, extra_json
                )
                VALUES (
                    :interface_id, :interface_key, :interface_name, :test_result,
                    :latency_ms, :error_message, :tested_by, :response_summary, CAST(:extra_json AS jsonb)
                )
                RETURNING *
                """
            ),
            {**row, "extra_json": dumps_json(row["extra_json"])},
        ).mappings().first()
    return mapping_dict(inserted)


def list_api_test_logs(
    *,
    interface_name: str = "",
    result: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    limit_value = max(1, min(int(limit or 100), 500))
    engine = security_postgres_engine()
    if engine is None:
        rows = list(reversed(_API_TEST_MEMORY))
        if interface_name:
            rows = [row for row in rows if interface_name.lower() in str(row.get("interface_name") or "").lower()]
        if result:
            rows = [row for row in rows if str(row.get("test_result") or "") == result]
        return rows[:limit_value]
    where = []
    params: dict[str, Any] = {"limit": limit_value}
    if interface_name:
        where.append("interface_name ILIKE :interface_name")
        params["interface_name"] = f"%{interface_name}%"
    if result:
        where.append("test_result = :result")
        params["result"] = result
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM system_api_test_logs
                {where_sql}
                ORDER BY tested_at DESC, id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
    return mapping_list(rows)


def list_role_permissions() -> list[dict[str, Any]]:
    engine = security_postgres_engine()
    if engine is None:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT role_id, role_name, permissions_json, description, created_at, updated_at
                FROM roles
                ORDER BY role_id
                """
            )
        ).mappings().all()
    values = []
    for row in mapping_list(rows):
        row["permissions"] = loads_json(row.get("permissions_json"), default=[])
        row.pop("permissions_json", None)
        values.append(row)
    return values


def upsert_role_permissions(role_id: str, permissions: list[str], *, role_name: str = "", description: str = "") -> dict[str, Any]:
    role = str(role_id or "").strip()
    if not role:
        raise ValueError("role_id is required")
    engine = security_postgres_engine()
    if engine is None:
        return {"role_id": role, "role_name": role_name or role, "permissions": permissions, "description": description}
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO roles (role_id, role_name, permissions_json, description, updated_at)
                VALUES (:role_id, :role_name, CAST(:permissions_json AS jsonb), :description, CURRENT_TIMESTAMP)
                ON CONFLICT (role_id) DO UPDATE SET
                    role_name = EXCLUDED.role_name,
                    permissions_json = EXCLUDED.permissions_json,
                    description = EXCLUDED.description,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING role_id, role_name, permissions_json, description, created_at, updated_at
                """
            ),
            {
                "role_id": role,
                "role_name": role_name or role,
                "permissions_json": dumps_json(sorted(set(permissions))),
                "description": description,
            },
        ).mappings().first()
    value = mapping_dict(row)
    value["permissions"] = loads_json(value.get("permissions_json"), default=[])
    value.pop("permissions_json", None)
    return value
