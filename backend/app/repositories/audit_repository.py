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
    if user:
        masked_metadata = {
            **masked_metadata,
            "_workspace_id": user.workspace_id,
        }
    engine = postgres_engine()
    if engine is None:
        _MEMORY_AUDIT_LOGS.append(
            {
                "id": len(_MEMORY_AUDIT_LOGS) + 1,
                "actor": user.username if user else "",
                "role_id": user.role if user else "",
                "tenant_id": user.tenant_id if user else "default",
                "workspace_id": user.workspace_id if user else "default",
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
                        status, request_id, ip_address, metadata_json, tenant_id
                    )
                    VALUES (
                        :actor, :role_id, :action, :resource_type, :resource_id,
                        :status, :request_id, :ip_address, CAST(:metadata_json AS jsonb),
                        :tenant_id
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
                    "tenant_id": user.tenant_id if user else "default",
                },
            )
        return True
    except Exception:
        return False


def list_audit_logs(
    limit: int = 100,
    action: str | None = None,
    *,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> list[dict[str, Any]]:
    engine = security_postgres_engine()
    if engine is None:
        rows = [
            row
            for row in _MEMORY_AUDIT_LOGS
            if (not action or row.get("action") == action)
            and (tenant_id is None or str(row.get("tenant_id") or "default") == str(tenant_id))
            and (workspace_id is None or str(row.get("workspace_id") or "default") == str(workspace_id))
        ]
        return list(reversed(rows))[: max(1, min(int(limit or 100), 500))]
    params: dict[str, Any] = {"limit": max(1, min(int(limit or 100), 500))}
    clauses: list[str] = []
    if action:
        clauses.append("action = :action")
        params["action"] = action
    if tenant_id is not None:
        clauses.append("tenant_id = :tenant_id")
        params["tenant_id"] = str(tenant_id)
    if workspace_id is not None:
        clauses.append("COALESCE(metadata_json->>'_workspace_id', 'default') = :workspace_id")
        params["workspace_id"] = str(workspace_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, actor, role_id, action, resource_type, resource_id,
                           status, request_id, ip_address, metadata_json,
                           tenant_id, created_at
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
