from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from backend.app.auth.jwt import create_access_token
from backend.app.auth.password import hash_password, validate_password_length, verify_password
from backend.app.core.config import get_settings
from backend.app.core.security import CurrentUser, ROLE_PERMISSIONS, get_current_user
from backend.app.repositories.audit_repository import write_audit_log
from backend.app.repositories.user_repository import get_user_by_username, update_last_login, update_password


router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _validate_new_password_length(cls, value: str) -> str:
        return validate_password_length(value)


def _user_payload(user: CurrentUser, display_name: str = "", email: str = "") -> dict:
    return {
        "id": user.user_id,
        "username": user.username,
        "email": email,
        "display_name": display_name or user.username,
        "role": user.role,
        "permissions": user.permissions,
        "auth_mode": user.auth_mode,
        "tenant_id": user.tenant_id,
        "workspace_id": user.workspace_id,
        "role_ids": list(user.role_ids),
    }


@router.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> dict:
    record = get_user_by_username(payload.username)
    ip_address = request.client.host if request.client else ""
    if not record or not record.get("is_active", True) or not verify_password(payload.password, str(record.get("password_hash") or "")):
        write_audit_log(
            action="auth.login_failed",
            resource_type="auth",
            status="failed",
            ip_address=ip_address,
            metadata={"username": payload.username, "reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    role = str(record.get("role") or "viewer")
    permissions = sorted(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["viewer"]))
    user = CurrentUser(
        user_id=str(record.get("user_id") or payload.username),
        username=str(record.get("username") or payload.username),
        role=role,
        permissions=permissions,
        auth_mode="jwt",
        tenant_id=str(record.get("tenant_id") or "default"),
        workspace_id=str(record.get("workspace_id") or "default"),
        role_ids=tuple(record.get("role_ids") or (role,)),
    )
    token = create_access_token(
        subject=user.username,
        user_id=user.user_id,
        role=user.role,
        permissions=user.permissions,
        extra={"tenant_id": user.tenant_id, "workspace_id": user.workspace_id, "role_ids": list(user.role_ids)},
    )
    update_last_login(user.username)
    write_audit_log(
        action="auth.login_success",
        user=user,
        resource_type="auth",
        status="success",
        ip_address=ip_address,
        metadata={"username": user.username, "role": user.role},
    )
    expires_in = max(60, int(get_settings().jwt_access_token_expire_minutes) * 60)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": _user_payload(user, display_name=str(record.get("display_name") or ""), email=str(record.get("email") or "")),
    }


@router.get("/api/auth/me")
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict:
    record = get_user_by_username(user.username) or {}
    return {"user": _user_payload(user, display_name=str(record.get("display_name") or ""), email=str(record.get("email") or ""))}


@router.post("/api/auth/logout")
def logout(request: Request, user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict:
    write_audit_log(
        action="auth.logout",
        user=user,
        resource_type="auth",
        status="success",
        ip_address=request.client.host if request.client else "",
        metadata={"username": user.username},
    )
    return {"ok": True}


@router.post("/api/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    record = get_user_by_username(user.username)
    if not record or not verify_password(payload.old_password, str(record.get("password_hash") or "")):
        write_audit_log(
            action="auth.password_change",
            user=user,
            resource_type="auth",
            status="failed",
            ip_address=request.client.host if request.client else "",
            metadata={"reason": "old_password_invalid"},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
    ok = update_password(user.username, hash_password(payload.new_password))
    write_audit_log(
        action="auth.password_change",
        user=user,
        resource_type="auth",
        status="success" if ok else "failed",
        ip_address=request.client.host if request.client else "",
        metadata={"updated": ok},
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="密码更新失败")
    return {"ok": True}
