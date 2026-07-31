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
        "auth:self",
        "dashboard:read",
        "forecast:read",
        "forecast:run",
        "data:read",
        "data:export",
        "data:query",
        "data:sync",
        "task:read",
        "assistant:use",
        "assistant:export",
        "knowledge:read",
        "knowledge:write",
        "knowledge:export",
        "report:read",
        "report:download",
        "report:generate",
        "model:read",
        "strategy:read",
        "strategy:generate",
        "strategy:submit",
    },
    "developer": {
        "auth:self",
        "dashboard:read",
        "forecast:read",
        "data:read",
        "data:export",
        "data:query",
        "task:read",
        "task:diagnostics",
        "assistant:use",
        "assistant:export",
        "assistant:debug",
        "knowledge:read",
        "knowledge:export",
        "report:read",
        "report:download",
        "model:read",
        "model:export",
        "strategy:read",
        "trace:read",
        "security:read",
        "system:diagnostics",
        "settings:read",
        "audit:read",
        "user:read",
    },
    "viewer": {
        "auth:self",
        "dashboard:read",
        "forecast:read",
        "knowledge:read",
        "report:read",
        "strategy:read",
    },
    "reviewer": {
        "auth:self",
        "dashboard:read",
        "forecast:read",
        "knowledge:read",
        "report:read",
        "report:download",
        "report:review",
        "strategy:read",
        "strategy:review",
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
    raw_role = str(role or "").strip().lower()
    if raw_role not in ROLE_PERMISSIONS:
        return []
    normalized = normalize_role(raw_role)
    return sorted(ROLE_PERMISSIONS.get(normalized, set()))


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authorization_bearer(request: Request) -> str:
    value = str(request.headers.get("Authorization") or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value.split(" ", 1)[1].strip()


def _current_user_from_jwt(request: Request, token: str) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise _unauthorized("登录令牌无效或已过期") from exc
    username = str(payload.get("sub") or "").strip()
    if not username:
        raise _unauthorized("登录令牌缺少用户信息")
    record = get_user_by_username(username)
    if not record or not record.get("is_active", True):
        raise _unauthorized("用户不存在或已停用")
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
        raise _unauthorized("缺少登录令牌")
    if settings.auth_required or settings.is_production:
        raise _unauthorized("认证模式要求使用 Bearer token")
    if settings.app_env not in {"development", "test"}:
        raise _unauthorized("当前环境不允许开发身份头")
    role = role or "viewer"
    auth_mode = "development_header"
    role = normalize_role(role) if role in ROLE_PERMISSIONS else ""
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
