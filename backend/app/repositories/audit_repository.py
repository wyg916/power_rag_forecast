from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.core.redaction import mask_secret_fields
from backend.app.core.security import CurrentUser

from .base import dumps_json, mapping_list, security_postgres_engine as _security_postgres_engine

# Compatibility seam; callers still receive the dedicated security engine.
postgres_engine = _security_postgres_engine


def security_postgres_engine():
    return postgres_engine()

_MEMORY_AUDIT_LOGS: list[dict[str, Any]] = []


def clear_memory_audit_logs() -> None:
    _MEMORY_AUDIT_LOGS.clear()


def write_audit_log(
    *,
    action: str,
    user: CurrentUser | None = None,
    resource_type: str = "",
    resource_id: str = "",
    status: str = "success",
    request_id: str = "",
    ip_address: str = "",
    metadata: dict[str, Any] | None = None,
) -> bool:
    masked_metadata = mask_secret_fields(metadata or {})
    engine = postgres_engine()
    if engine is None:
        _MEMORY_AUDIT_LOGS.append(
            {
                "id": len(_MEMORY_AUDIT_LOGS) + 1,
                "actor": user.username if user else "",
                "role_id": user.role if user else "",
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "status": status,
                "request_id": request_id,
                "ip_address": ip_address,
                "metadata_json": masked_metadata,
            }
        )
        return False
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO audit_logs (
                        actor, role_id, action, resource_type, resource_id,
                        status, request_id, ip_address, metadata_json
                    )
                    VALUES (
                        :actor, :role_id, :action, :resource_type, :resource_id,
                        :status, :request_id, :ip_address, CAST(:metadata_json AS jsonb)
                    )
                    """
                ),
                {
                    "actor": user.username if user else "",
                    "role_id": user.role if user else "",
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "status": status,
                    "request_id": request_id,
                    "ip_address": ip_address,
                    "metadata_json": dumps_json(masked_metadata),
                },
            )
        return True
    except Exception:
        return False


def list_audit_logs(limit: int = 100, action: str | None = None) -> list[dict[str, Any]]:
    engine = security_postgres_engine()
    if engine is None:
        rows = [row for row in _MEMORY_AUDIT_LOGS if not action or row.get("action") == action]
        return list(reversed(rows))[: max(1, min(int(limit or 100), 500))]
    params: dict[str, Any] = {"limit": max(1, min(int(limit or 100), 500))}
    where = ""
    if action:
        where = "WHERE action = :action"
        params["action"] = action
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, actor, role_id, action, resource_type, resource_id,
                           status, request_id, ip_address, metadata_json, created_at
                    FROM audit_logs
                    {where}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
    except Exception:
        return []
    return mapping_list(rows)
