from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ....config import APP_VERSION, PLATFORM_NAME
from ....core.security import CurrentUser, ROLE_PERMISSIONS, get_current_user, require_permission
from ....data_access import latest_business_summary
from ....repositories.audit_repository import list_audit_logs
from ....services.ui_platform_service import response, save_system_config, system_config_snapshot, system_health_snapshot
from ....data_access import database_runtime_status
from backend.app.ai_assistant.core.llm_client import get_local_llm_status


router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return {"ok": True, "platform": PLATFORM_NAME, "version": APP_VERSION}


@router.get("/health")
def root_health() -> dict:
    return health()


@router.get("/api/db/health")
def db_health() -> dict:
    status = database_runtime_status()
    return {
        "ok": bool(status.get("active") == "postgresql"),
        "active": status.get("active"),
        "message": status.get("message"),
    }


@router.get("/api/settings/config")
def settings_config(_: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))]) -> dict:
    return response(system_config_snapshot(), data_source="runtime_config")


@router.post("/api/settings/config")
def settings_config_save(
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
) -> dict:
    result = save_system_config(payload, user=user, ip_address=request.client.host if request.client else "")
    return response(result, data_source="runtime_config")


@router.get("/api/settings/health")
def settings_health(_: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))]) -> dict:
    return response(system_health_snapshot(), data_source="runtime_probe")


@router.get("/api/ai/local-model/status")
def local_model_status(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    try:
        return get_local_llm_status()
    except Exception as exc:
        return {"available": False, "message": str(exc)}


@router.get("/api/business-summary")
def business_summary() -> dict:
    return {"records": latest_business_summary()}


@router.get("/api/security/me")
def security_me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "permissions": user.permissions,
        "auth_mode": user.auth_mode,
    }


@router.get("/api/security/permissions")
def security_permissions(_: Annotated[CurrentUser, Depends(require_permission("security:read"))]) -> dict:
    return {"roles": {role: sorted(permissions) for role, permissions in ROLE_PERMISSIONS.items()}}


@router.get("/api/audit/logs")
def audit_logs(
    request: Request,
    _: Annotated[CurrentUser, Depends(require_permission("audit:read"))],
    limit: int = 100,
    action: str | None = None,
) -> dict:
    return {"logs": list_audit_logs(limit=limit, action=action)}
