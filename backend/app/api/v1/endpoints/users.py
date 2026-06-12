from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.app.auth.password import hash_password
from backend.app.core.security import CurrentUser, ROLE_PERMISSIONS, require_permission
from backend.app.repositories.audit_repository import write_audit_log
from backend.app.repositories.user_repository import (
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
from backend.app.schemas import UserCreateRequest, UserResetPasswordRequest, UserUpdateRequest


router = APIRouter()

ROLE_LABELS = {
    "admin": "管理员",
    "analyst": "分析员",
    "viewer": "查看者",
    "developer": "开发者",
}

ROLE_DESCRIPTIONS = {
    "admin": "全权限，包含用户管理、审计、任务和系统配置。",
    "analyst": "可查看预测、生成报告、使用 AI 助手并触发普通分析任务。",
    "viewer": "只读查看和普通 AI 问答，不能触发长任务或 debug。",
    "developer": "可查看 debug、trace 和模型路由信息，默认不具备业务写权限。",
}


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _validate_email(email: str | None) -> str:
    value = str(email or "").strip()
    if value and ("@" not in value or value.startswith("@") or value.endswith("@")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email 格式不正确")
    return value


def _target_or_404(user_id: str) -> dict:
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


@router.get("/api/users/roles")
def user_roles(_: Annotated[CurrentUser, Depends(require_permission("user:read"))], request: Request) -> dict:
    roles = []
    for name in ["admin", "analyst", "viewer", "developer"]:
        roles.append(
            {
                "name": name,
                "label": ROLE_LABELS[name],
                "description": ROLE_DESCRIPTIONS[name],
                "permissions": sorted(ROLE_PERMISSIONS.get(name, set())),
            }
        )
    return {"roles": roles}


@router.get("/api/users")
def user_list(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:read"))],
    keyword: str = Query(default="", max_length=128),
    role: str | None = Query(default=None, max_length=32),
    is_active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    result = list_users(keyword=keyword, role=role, is_active=is_active, page=page, page_size=page_size)
    write_audit_log(
        action="user.list",
        user=user,
        resource_type="user",
        status="success",
        ip_address=_ip(request),
        metadata={"keyword": keyword, "role": role, "is_active": is_active, "page": page, "page_size": page_size},
    )
    return result


@router.post("/api/users", status_code=status.HTTP_201_CREATED)
def user_create(
    payload: UserCreateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    username = payload.username.strip()
    if get_user_by_username(username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    email = _validate_email(payload.email)
    role = normalize_role(payload.role)
    created = create_user(
        username=username,
        email=email,
        display_name=payload.display_name.strip() or username,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=payload.is_active,
        is_superuser=role == "admin",
    )
    write_audit_log(
        action="user.create",
        user=user,
        resource_type="user",
        resource_id=str(created.get("user_id") or username),
        status="success",
        ip_address=_ip(request),
        metadata={"target_username": username, "role": role, "is_active": payload.is_active},
    )
    return {"user": public_user(created)}


@router.patch("/api/users/{user_id}")
def user_update(
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    current = _target_or_404(user_id)
    new_role = normalize_role(payload.role) if payload.role is not None else str(current.get("role") or "viewer")
    new_active = bool(payload.is_active) if payload.is_active is not None else bool(current.get("is_active", True))
    try:
        ensure_not_last_admin_demoted_or_disabled(user_id, new_role=new_role, new_is_active=new_active)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    email = _validate_email(payload.email) if payload.email is not None else None
    updated = update_user(
        user_id,
        email=email,
        display_name=payload.display_name.strip() if payload.display_name is not None else None,
        role=new_role,
        is_active=new_active,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    metadata = {
        "target_user_id": str(current.get("user_id") or user_id),
        "target_username": current.get("username"),
        "old_role": current.get("role"),
        "new_role": new_role,
        "old_is_active": current.get("is_active"),
        "new_is_active": new_active,
    }
    action = "user.update"
    if normalize_role(str(current.get("role") or "")) != new_role:
        write_audit_log(action="user.role_update", user=user, resource_type="user", resource_id=user_id, ip_address=_ip(request), metadata=metadata)
    if bool(current.get("is_active", True)) != new_active:
        write_audit_log(
            action="user.enable" if new_active else "user.disable",
            user=user,
            resource_type="user",
            resource_id=user_id,
            ip_address=_ip(request),
            metadata=metadata,
        )
    write_audit_log(action=action, user=user, resource_type="user", resource_id=user_id, ip_address=_ip(request), metadata=metadata)
    return {"user": public_user(updated)}


@router.post("/api/users/{user_id}/reset-password")
def user_reset_password(
    user_id: str,
    payload: UserResetPasswordRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    target = _target_or_404(user_id)
    ok = update_password_hash(user_id, hash_password(payload.new_password))
    write_audit_log(
        action="user.password_reset",
        user=user,
        resource_type="user",
        resource_id=user_id,
        status="success" if ok else "failed",
        ip_address=_ip(request),
        metadata={"target_user_id": user_id, "target_username": target.get("username")},
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="密码重置失败")
    return {"ok": True}


@router.delete("/api/users/{user_id}")
def user_disable(
    user_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("user:write"))],
) -> dict:
    current = _target_or_404(user_id)
    try:
        ensure_not_last_admin_demoted_or_disabled(user_id, new_is_active=False)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    updated = set_user_active(user_id, False)
    write_audit_log(
        action="user.disable",
        user=user,
        resource_type="user",
        resource_id=user_id,
        ip_address=_ip(request),
        metadata={"target_user_id": user_id, "target_username": current.get("username"), "old_is_active": current.get("is_active"), "new_is_active": False},
    )
    return {"user": public_user(updated or current)}

