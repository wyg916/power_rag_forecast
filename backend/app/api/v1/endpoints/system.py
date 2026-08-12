from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ....config import APP_VERSION, PLATFORM_NAME
from ....core.security import CurrentUser, ROLE_PERMISSIONS, get_current_user, require_permission
from ....data_access import latest_business_summary
from ....auth.password import hash_password
from ....repositories.audit_repository import list_audit_logs, write_audit_log
from ....repositories.user_repository import (
    create_user,
    ensure_not_last_admin_demoted_or_disabled,
    get_user_by_id,
    get_user_by_username,
    list_users,
    normalize_role,
    public_user,
    set_user_active,
    update_password_hash,
    update_user,
)
from ....schemas import UserCreateRequest, UserResetPasswordRequest, UserUpdateRequest
from ....services import settings_center_service as settings_center
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
        "tenant_id": user.tenant_id,
        "workspace_id": user.workspace_id,
    }


@router.get("/api/security/permissions")
def security_permissions(_: Annotated[CurrentUser, Depends(require_permission("security:read"))]) -> dict:
    return {"roles": {role: sorted(permissions) for role, permissions in ROLE_PERMISSIONS.items()}}


@router.get("/api/audit/logs")
def audit_logs(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("audit:read"))],
    limit: int = 100,
    action: str | None = None,
) -> dict:
    return {
        "logs": list_audit_logs(
            limit=limit,
            action=action,
            tenant_id=user.tenant_id,
            workspace_id=user.workspace_id,
        )
    }


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _validate_email(email: str | None) -> str:
    value = str(email or "").strip()
    if value and ("@" not in value or value.startswith("@") or value.endswith("@")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email 格式不正确")
    return value


def _target_or_404(user_id: str, actor: CurrentUser) -> dict:
    target = get_user_by_id(
        user_id,
        tenant_id=actor.tenant_id,
        workspace_id=actor.workspace_id,
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return target


@router.get("/api/settings/status/overview")
def settings_status_overview(user: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))]) -> dict:
    return settings_center.system_status_overview(user=user)


@router.get("/api/settings/status/summary")
def settings_status_summary(_: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))]) -> dict:
    return {"items": settings_center.system_status_summary()}


@router.get("/api/settings/status/health-details")
def settings_health_details(_: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))]) -> dict:
    return {"items": settings_center.system_health_details()}


@router.get("/api/settings/runtime-config")
def settings_runtime_config(_: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))]) -> dict:
    return settings_center.get_runtime_config_payload()


@router.put("/api/settings/runtime-config")
def settings_runtime_config_update(
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
) -> dict:
    return settings_center.update_runtime_config_payload(payload, user=user, ip_address=_ip(request))


@router.get("/api/settings/status/check-records")
def settings_check_records(
    _: Annotated[CurrentUser, Depends(require_permission("dashboard:read"))],
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"items": settings_center.health_records(limit=limit)}


@router.get("/api/settings/status/task-queue-snapshot")
def settings_task_queue_snapshot(_: Annotated[CurrentUser, Depends(require_permission("task:read"))]) -> dict:
    return settings_center.task_queue_snapshot()


@router.get("/api/settings/users/overview")
def settings_users_overview(user: Annotated[CurrentUser, Depends(require_permission("user:read"))]) -> dict:
    return settings_center.users_overview(user=user)


@router.get("/api/settings/users")
def settings_users(
    user: Annotated[CurrentUser, Depends(require_permission("user:read"))],
    keyword: str = Query(default="", max_length=128),
    role: str | None = Query(default=None, max_length=32),
    status_value: str = Query(default="", alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    is_active = None
    if status_value in {"active", "enabled", "online"}:
        is_active = True
    elif status_value in {"disabled", "inactive", "locked"}:
        is_active = False
    return list_users(
        keyword=keyword,
        role=role,
        is_active=is_active,
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
        page=page,
        page_size=page_size,
    )


@router.post("/api/settings/users", status_code=status.HTTP_201_CREATED)
def settings_user_create(
    payload: UserCreateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    username = payload.username.strip()
    if get_user_by_username(username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    role = normalize_role(payload.role)
    created = create_user(
        username=username,
        email=_validate_email(payload.email),
        display_name=payload.display_name.strip() or username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=payload.is_active,
        is_superuser=role == "admin",
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
    )
    write_audit_log(
        action="settings.user.create",
        user=user,
        resource_type="user",
        resource_id=str(created.get("user_id") or username),
        status="success",
        ip_address=_ip(request),
        metadata={"target_username": username, "role": role, "is_active": payload.is_active},
    )
    return {"user": public_user(created)}


@router.put("/api/settings/users/{user_id}")
def settings_user_update(
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    current = _target_or_404(user_id, user)
    new_role = normalize_role(payload.role) if payload.role is not None else str(current.get("role") or "viewer")
    new_active = bool(payload.is_active) if payload.is_active is not None else bool(current.get("is_active", True))
    try:
        ensure_not_last_admin_demoted_or_disabled(
            user_id,
            new_role=new_role,
            new_is_active=new_active,
            tenant_id=user.tenant_id,
            workspace_id=user.workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    updated = update_user(
        user_id,
        email=_validate_email(payload.email) if payload.email is not None else None,
        display_name=payload.display_name.strip() if payload.display_name is not None else None,
        role=new_role,
        is_active=new_active,
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
    )
    write_audit_log(
        action="settings.user.update",
        user=user,
        resource_type="user",
        resource_id=user_id,
        status="success",
        ip_address=_ip(request),
        metadata={"target_username": current.get("username"), "old_role": current.get("role"), "new_role": new_role, "new_is_active": new_active},
    )
    return {"user": public_user(updated or current)}


@router.post("/api/settings/users/{user_id}/disable")
def settings_user_disable(
    user_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    current = _target_or_404(user_id, user)
    try:
        ensure_not_last_admin_demoted_or_disabled(
            user_id,
            new_is_active=False,
            tenant_id=user.tenant_id,
            workspace_id=user.workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    updated = set_user_active(
        user_id,
        False,
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
    )
    write_audit_log(
        action="settings.user.disable",
        user=user,
        resource_type="user",
        resource_id=user_id,
        status="success",
        ip_address=_ip(request),
        metadata={"target_username": current.get("username")},
    )
    return {"user": public_user(updated or current)}


@router.post("/api/settings/users/{user_id}/enable")
def settings_user_enable(
    user_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    current = _target_or_404(user_id, user)
    updated = set_user_active(
        user_id,
        True,
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
    )
    write_audit_log(
        action="settings.user.enable",
        user=user,
        resource_type="user",
        resource_id=user_id,
        status="success",
        ip_address=_ip(request),
        metadata={"target_username": current.get("username")},
    )
    return {"user": public_user(updated or current)}


@router.post("/api/settings/users/{user_id}/reset-password")
def settings_user_reset_password(
    user_id: str,
    payload: UserResetPasswordRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    current = _target_or_404(user_id, user)
    ok = update_password_hash(
        user_id,
        hash_password(payload.new_password),
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
    )
    write_audit_log(
        action="settings.user.password_reset",
        user=user,
        resource_type="user",
        resource_id=user_id,
        status="success" if ok else "failed",
        ip_address=_ip(request),
        metadata={"target_username": current.get("username")},
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="密码重置失败")
    return {"ok": True}


@router.post("/api/settings/users/{user_id}/assign-role")
def settings_user_assign_role(
    user_id: str,
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    current = _target_or_404(user_id, user)
    role = normalize_role(str(payload.get("role") or payload.get("role_id") or "viewer"))
    try:
        ensure_not_last_admin_demoted_or_disabled(
            user_id,
            new_role=role,
            tenant_id=user.tenant_id,
            workspace_id=user.workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    updated = update_user(
        user_id,
        role=role,
        tenant_id=user.tenant_id,
        workspace_id=user.workspace_id,
    )
    write_audit_log(
        action="settings.user.assign_role",
        user=user,
        resource_type="user",
        resource_id=user_id,
        status="success",
        ip_address=_ip(request),
        metadata={"target_username": current.get("username"), "old_role": current.get("role"), "new_role": role},
    )
    return {"user": public_user(updated or current)}


@router.delete("/api/settings/users/{user_id}")
def settings_user_delete(
    user_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    # Product safety: this is a soft delete/disable endpoint.
    return settings_user_disable(user_id, request, user)


@router.get("/api/settings/roles/permissions")
def settings_roles_permissions(_: Annotated[CurrentUser, Depends(require_permission("user:read"))]) -> dict:
    return settings_center.role_permissions_payload()


@router.put("/api/settings/roles/permissions")
def settings_roles_permissions_update(
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    try:
        return settings_center.update_role_permissions_payload(payload, user=user, ip_address=_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/api/settings/security-policy")
def settings_security_policy(_: Annotated[CurrentUser, Depends(require_permission("user:read"))]) -> dict:
    return settings_center.security_policy_payload()


@router.put("/api/settings/security-policy")
def settings_security_policy_update(
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
) -> dict:
    return settings_center.update_security_policy_payload(payload, user=user, ip_address=_ip(request))


@router.get("/api/settings/audit-logs")
def settings_audit_logs(
    user: Annotated[CurrentUser, Depends(require_permission("audit:read"))],
    limit: int = Query(default=100, ge=1, le=500),
    action: str | None = None,
) -> dict:
    return settings_center.settings_audit_logs(limit=limit, action=action, user=user)


@router.get("/api/settings/interfaces/overview")
def settings_interfaces_overview(_: Annotated[CurrentUser, Depends(require_permission("settings:write"))]) -> dict:
    return settings_center.interface_overview()


@router.get("/api/settings/interfaces/configs")
def settings_interfaces_configs(
    _: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
    keyword: str = Query(default="", max_length=128),
    interface_type: str = Query(default="", max_length=64),
    status_value: str = Query(default="", alias="status", max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> dict:
    return settings_center.interface_configs(keyword=keyword, interface_type=interface_type, status=status_value, page=page, page_size=page_size)


@router.put("/api/settings/interfaces/{interface_id}")
def settings_interface_update(
    interface_id: str,
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
) -> dict:
    try:
        return settings_center.update_interface_config(interface_id, payload, user=user, ip_address=_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/api/settings/interfaces/{interface_id}/test")
def settings_interface_test(
    interface_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
) -> dict:
    try:
        return settings_center.test_interface(interface_id, user=user, ip_address=_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/api/settings/interfaces/test-all")
def settings_interfaces_test_all(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
) -> dict:
    return settings_center.test_all_interfaces(user=user, ip_address=_ip(request))


@router.get("/api/settings/interfaces")
def settings_interfaces(
    _: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
    keyword: str = Query(default="", max_length=128),
    interface_type: str = Query(default="", max_length=64),
    status_value: str = Query(default="", alias="status", max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> dict:
    return settings_center.interfaces_payload(keyword=keyword, interface_type=interface_type, status=status_value, page=page, page_size=page_size)


@router.get("/api/settings/interfaces/test-logs")
def settings_interfaces_test_logs(
    _: Annotated[CurrentUser, Depends(require_permission("settings:write"))],
    interface_name: str = Query(default="", max_length=128),
    result: str = Query(default="", max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return settings_center.interface_test_logs(interface_name=interface_name, result=result, limit=limit)
