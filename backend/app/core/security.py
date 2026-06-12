from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, HTTPException, Request, status

from backend.app.auth.jwt import JWTError, decode_access_token
from backend.app.core.config import get_settings
from backend.app.repositories.user_repository import get_user_by_username, normalize_role


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "analyst": {
        "dashboard:read",
        "forecast:read",
        "forecast:run",
        "data:read",
        "data:sync",
        "task:read",
        "task:run",
        "assistant:use",
        "knowledge:read",
        "knowledge:write",
        "report:read",
        "report:generate",
        "report:review",
        "model:read",
    },
    "developer": {
        "dashboard:read",
        "forecast:read",
        "data:read",
        "task:read",
        "assistant:use",
        "assistant:debug",
        "knowledge:read",
        "report:read",
        "model:read",
        "trace:read",
        "security:read",
        "user:read",
    },
    "viewer": {
        "dashboard:read",
        "forecast:read",
        "data:read",
        "task:read",
        "assistant:use",
        "knowledge:read",
        "report:read",
        "model:read",
    },
}

# Backward compatible alias for earlier versions of the platform.
ROLE_PERMISSIONS["operator"] = ROLE_PERMISSIONS["analyst"]


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    username: str
    role: str
    permissions: list[str]
    auth_mode: str

    def has_permission(self, permission: str) -> bool:
        values = set(self.permissions)
        return "*" in values or permission in values

    def can_debug(self) -> bool:
        return self.has_permission("assistant:debug") or self.has_permission("trace:read")


def _permissions_for_role(role: str) -> list[str]:
    normalized = normalize_role(role)
    return sorted(ROLE_PERMISSIONS.get(normalized, ROLE_PERMISSIONS["viewer"]))


def _authorization_bearer(request: Request) -> str:
    value = str(request.headers.get("Authorization") or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value.split(" ", 1)[1].strip()


def _current_user_from_jwt(request: Request, token: str) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录令牌无效或已过期") from exc
    username = str(payload.get("sub") or "").strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录令牌缺少用户信息")
    record = get_user_by_username(username)
    if not record or not record.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")
    role = normalize_role(str(record.get("role") or payload.get("role") or "viewer"))
    user = CurrentUser(
        user_id=str(record.get("user_id") or payload.get("user_id") or username),
        username=username,
        role=role,
        permissions=_permissions_for_role(role),
        auth_mode="jwt",
    )
    request.state.current_user = user
    return user


def get_current_user(request: Request) -> CurrentUser:
    token = _authorization_bearer(request)
    if token:
        return _current_user_from_jwt(request, token)

    settings = get_settings()
    username = (request.headers.get("X-User") or request.headers.get("X-Username") or "").strip()
    role = (request.headers.get("X-Role") or "").strip().lower()
    if not username:
        if settings.auth_required:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少登录令牌")
        username = "dev_admin"
        role = role or "admin"
        auth_mode = "dev_header_fallback"
    else:
        if settings.auth_required:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="生产认证模式必须使用 Bearer token")
        role = role or "viewer"
        auth_mode = "header"
    role = normalize_role(role)
    user = CurrentUser(
        user_id=username,
        username=username,
        role=role,
        permissions=_permissions_for_role(role),
        auth_mode=auth_mode,
    )
    request.state.current_user = user
    return user


def optional_current_user(request: Request) -> CurrentUser | None:
    try:
        return get_current_user(request)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise


def require_permission(permission: str) -> Callable[[Request, CurrentUser], CurrentUser]:
    def dependency(request: Request, user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not user.has_permission(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"缺少权限：{permission}")
        request.state.current_user = user
        return user

    return dependency


def require_role(*roles: str) -> Callable[[Request, CurrentUser], CurrentUser]:
    allowed = {normalize_role(role) for role in roles}

    def dependency(request: Request, user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in allowed and not user.has_permission("*"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="角色权限不足")
        request.state.current_user = user
        return user

    return dependency
