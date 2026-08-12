from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text

from .base import mapping_dict, mapping_list, security_postgres_engine as _security_postgres_engine

# Compatibility seam for existing tests and local adapters. The implementation
# now resolves the dedicated security identity, not the business runtime engine.
postgres_engine = _security_postgres_engine


def security_postgres_engine():
    return postgres_engine()


ROLE_ALIASES = {"operator": "analyst"}
VALID_ROLES = {"admin", "analyst", "reviewer", "viewer", "developer", "operator"}

_MEMORY_USERS: dict[str, dict[str, Any]] = {}


def normalize_role(role: str | None) -> str:
    value = str(role or "viewer").strip().lower()
    value = ROLE_ALIASES.get(value, value)
    return value if value in VALID_ROLES else "viewer"


def clear_memory_users() -> None:
    _MEMORY_USERS.clear()


def _normalize_user(row: dict[str, Any]) -> dict[str, Any]:
    role = normalize_role(row.get("role") or row.get("role_id"))
    status = str(row.get("status") or "").lower()
    is_active = row.get("is_active")
    if is_active is None:
        is_active = status not in {"disabled", "inactive", "locked"}
    return {
        "id": row.get("id"),
        "user_id": str(row.get("user_id") or row.get("id") or row.get("username") or ""),
        "username": str(row.get("username") or ""),
        "email": row.get("email") or "",
        "display_name": row.get("display_name") or row.get("username") or "",
        "password_hash": row.get("password_hash") or "",
        "role": role,
        "role_id": role,
        "role_ids": list(row.get("role_ids") or [role]),
        "tenant_id": str(row.get("tenant_id") or "default"),
        "workspace_id": str(row.get("workspace_id") or "default"),
        "is_active": bool(is_active),
        "is_superuser": bool(row.get("is_superuser") or role == "admin"),
        "last_login_at": row.get("last_login_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    value = _normalize_user(user)
    value.pop("password_hash", None)
    return value


def _matches_filters(
    user: dict[str, Any],
    keyword: str = "",
    role: str | None = None,
    is_active: bool | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> bool:
    if keyword:
        haystack = " ".join(str(user.get(key) or "") for key in ["username", "email", "display_name"]).lower()
        if keyword.lower() not in haystack:
            return False
    if role and normalize_role(str(user.get("role") or "")) != normalize_role(role):
        return False
    if is_active is not None and bool(user.get("is_active")) is not bool(is_active):
        return False
    if tenant_id is not None and str(user.get("tenant_id") or "default") != str(tenant_id):
        return False
    if workspace_id is not None and str(user.get("workspace_id") or "default") != str(workspace_id):
        return False
    return True


def list_users(
    *,
    keyword: str = "",
    role: str | None = None,
    is_active: bool | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    engine = security_postgres_engine()
    if engine is None:
        rows = [public_user(user) for user in _MEMORY_USERS.values()]
        filtered = [
            user
            for user in rows
            if _matches_filters(
                user,
                keyword=keyword,
                role=role,
                is_active=is_active,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
        ]
        filtered.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        start = (page - 1) * page_size
        return {"items": filtered[start : start + page_size], "total": len(filtered), "page": page, "page_size": page_size}

    where = []
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    if keyword:
        where.append("(username ILIKE :keyword OR email ILIKE :keyword OR display_name ILIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if role:
        where.append("COALESCE(role, role_id, 'viewer') = :role")
        params["role"] = normalize_role(role)
    if is_active is not None:
        where.append("is_active = :is_active")
        params["is_active"] = bool(is_active)
    if tenant_id is not None:
        where.append("tenant_id = :tenant_id")
        params["tenant_id"] = str(tenant_id)
    if workspace_id is not None:
        where.append("workspace_id = :workspace_id")
        params["workspace_id"] = str(workspace_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    try:
        with engine.connect() as conn:
            total = conn.execute(text(f"SELECT COUNT(*) FROM users {where_sql}"), params).scalar_one()
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, user_id, username, email, display_name, role, role_id, status,
                           tenant_id, workspace_id, is_active, is_superuser,
                           last_login_at, created_at, updated_at
                    FROM users
                    {where_sql}
                    ORDER BY created_at DESC, username ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
        return {
            "items": [public_user(row) for row in mapping_list(rows)],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }
    except Exception as exc:
        raise RuntimeError(f"list users failed: {exc}") from exc


def get_user_by_username(username: str) -> dict[str, Any] | None:
    name = str(username or "").strip()
    if not name:
        return None
    engine = security_postgres_engine()
    if engine is None:
        value = _MEMORY_USERS.get(name)
        return dict(value) if value else None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT user_id, username, display_name, password_hash, role_id, status,
                           tenant_id, workspace_id,
                           email, role, is_active, is_superuser, last_login_at, created_at, updated_at
                    FROM users
                    WHERE username = :username
                    LIMIT 1
                    """
                ),
                {"username": name},
            ).mappings().first()
        return _normalize_user(mapping_dict(row)) if row else None
    except Exception:
        return None


def get_user_by_id(
    user_id: str,
    *,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any] | None:
    value = str(user_id or "").strip()
    if not value:
        return None
    engine = security_postgres_engine()
    if engine is None:
        for user in _MEMORY_USERS.values():
            if str(user.get("user_id")) == value or str(user.get("id")) == value:
                if _matches_filters(user, tenant_id=tenant_id, workspace_id=workspace_id):
                    return dict(user)
                return None
        return None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT user_id, username, display_name, password_hash, role_id, status,
                           tenant_id, workspace_id,
                           email, role, is_active, is_superuser, last_login_at, created_at, updated_at
                    FROM users
                    WHERE (user_id = :user_id OR CAST(id AS TEXT) = :user_id)
                      AND (:tenant_id IS NULL OR tenant_id = :tenant_id)
                      AND (:workspace_id IS NULL OR workspace_id = :workspace_id)
                    LIMIT 1
                    """
                ),
                {
                    "user_id": value,
                    "tenant_id": str(tenant_id) if tenant_id is not None else None,
                    "workspace_id": str(workspace_id) if workspace_id is not None else None,
                },
            ).mappings().first()
        return _normalize_user(mapping_dict(row)) if row else None
    except Exception:
        return None


def create_user(
    *,
    username: str,
    password_hash: str,
    email: str = "",
    display_name: str = "",
    role: str = "viewer",
    is_active: bool = True,
    is_superuser: bool | None = None,
    tenant_id: str = "default",
    workspace_id: str = "default",
) -> dict[str, Any]:
    name = str(username or "").strip()
    if not name:
        raise ValueError("username is required")
    role_value = normalize_role(role)
    superuser = bool(is_superuser if is_superuser is not None else role_value == "admin")
    existing = get_user_by_username(name)
    if existing:
        return existing
    user_id = uuid.uuid4().hex
    engine = security_postgres_engine()
    if engine is None:
        now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
        user = _normalize_user(
            {
                "id": len(_MEMORY_USERS) + 1,
                "user_id": user_id,
                "username": name,
                "email": email,
                "display_name": display_name or name,
                "password_hash": password_hash,
                "role": role_value,
                "role_id": role_value,
                "tenant_id": str(tenant_id or "default"),
                "workspace_id": str(workspace_id or "default"),
                "status": "active" if is_active else "inactive",
                "is_active": is_active,
                "is_superuser": superuser,
                "created_at": now,
                "updated_at": now,
            }
        )
        _MEMORY_USERS[name] = user
        return dict(user)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (
                    user_id, username, email, display_name, password_hash,
                    role, role_id, status, tenant_id, workspace_id,
                    is_active, is_superuser, updated_at
                )
                VALUES (
                    :user_id, :username, :email, :display_name, :password_hash,
                    :role, :role_id, :status, :tenant_id, :workspace_id,
                    :is_active, :is_superuser, CURRENT_TIMESTAMP
                )
                ON CONFLICT (username) DO NOTHING
                """
            ),
            {
                "user_id": user_id,
                "username": name,
                "email": email,
                "display_name": display_name or name,
                "password_hash": password_hash,
                "role": role_value,
                "role_id": role_value,
                "status": "active" if is_active else "inactive",
                "tenant_id": str(tenant_id or "default"),
                "workspace_id": str(workspace_id or "default"),
                "is_active": is_active,
                "is_superuser": superuser,
            },
        )
    return get_user_by_username(name) or {}


def update_user(
    user_id: str,
    *,
    email: str | None = None,
    display_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any] | None:
    current = get_user_by_id(user_id, tenant_id=tenant_id, workspace_id=workspace_id)
    if not current:
        return None
    role_value = normalize_role(role) if role is not None else str(current.get("role") or "viewer")
    active_value = bool(is_active) if is_active is not None else bool(current.get("is_active", True))
    engine = security_postgres_engine()
    if engine is None:
        for username, user in _MEMORY_USERS.items():
            if str(user.get("user_id")) == str(user_id) or str(user.get("id")) == str(user_id):
                user.update(
                    {
                        "email": email if email is not None else user.get("email", ""),
                        "display_name": display_name if display_name is not None else user.get("display_name", ""),
                        "role": role_value,
                        "role_id": role_value,
                        "status": "active" if active_value else "inactive",
                        "is_active": active_value,
                        "is_superuser": role_value == "admin",
                        "updated_at": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
                    }
                )
                _MEMORY_USERS[username] = _normalize_user(user)
                return dict(_MEMORY_USERS[username])
        return None
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE users
                    SET email = COALESCE(:email, email),
                        display_name = COALESCE(:display_name, display_name),
                        role = :role,
                        role_id = :role,
                        status = :status,
                        is_active = :is_active,
                        is_superuser = :is_superuser,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE (user_id = :user_id OR CAST(id AS TEXT) = :user_id)
                      AND (:tenant_id IS NULL OR tenant_id = :tenant_id)
                      AND (:workspace_id IS NULL OR workspace_id = :workspace_id)
                    """
                ),
                {
                    "user_id": str(user_id),
                    "email": email,
                    "display_name": display_name,
                    "role": role_value,
                    "status": "active" if active_value else "inactive",
                    "is_active": active_value,
                    "is_superuser": role_value == "admin",
                    "tenant_id": str(tenant_id) if tenant_id is not None else None,
                    "workspace_id": str(workspace_id) if workspace_id is not None else None,
                },
            )
        return get_user_by_id(user_id, tenant_id=tenant_id, workspace_id=workspace_id)
    except Exception as exc:
        raise RuntimeError(f"update user failed: {exc}") from exc


def set_user_active(
    user_id: str,
    is_active: bool,
    *,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any] | None:
    return update_user(
        user_id,
        is_active=bool(is_active),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )


def update_user_role(
    user_id: str,
    role: str,
    *,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any] | None:
    return update_user(
        user_id,
        role=role,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )


def update_password_hash(
    user_id: str,
    password_hash: str,
    *,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> bool:
    current = get_user_by_id(user_id, tenant_id=tenant_id, workspace_id=workspace_id)
    if not current:
        return False
    username = str(current.get("username") or "")
    return update_password(username, password_hash)


def count_admin_users(
    *,
    active_only: bool = True,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> int:
    engine = security_postgres_engine()
    if engine is None:
        return sum(
            1
            for user in _MEMORY_USERS.values()
            if normalize_role(str(user.get("role") or "")) == "admin"
            and (not active_only or bool(user.get("is_active", True)))
            and _matches_filters(user, tenant_id=tenant_id, workspace_id=workspace_id)
        )
    where_active = "AND is_active = TRUE" if active_only else ""
    where_scope = ""
    params: dict[str, Any] = {}
    if tenant_id is not None:
        where_scope += " AND tenant_id = :tenant_id"
        params["tenant_id"] = str(tenant_id)
    if workspace_id is not None:
        where_scope += " AND workspace_id = :workspace_id"
        params["workspace_id"] = str(workspace_id)
    try:
        with engine.connect() as conn:
            value = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM users WHERE COALESCE(role, role_id) = 'admin' "
                    f"{where_active}{where_scope}"
                ),
                params,
            ).scalar_one()
        return int(value or 0)
    except Exception:
        return 0


def ensure_not_last_admin_demoted_or_disabled(
    user_id: str,
    *,
    new_role: str | None = None,
    new_is_active: bool | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> None:
    current = get_user_by_id(user_id, tenant_id=tenant_id, workspace_id=workspace_id)
    if not current:
        raise ValueError("user not found")
    if normalize_role(str(current.get("role") or "")) != "admin":
        return
    would_remain_admin = normalize_role(new_role) == "admin" if new_role is not None else True
    would_remain_active = bool(new_is_active) if new_is_active is not None else bool(current.get("is_active", True))
    if would_remain_admin and would_remain_active:
        return
    if count_admin_users(
        active_only=True,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    ) <= 1:
        raise ValueError("不能禁用或降级最后一个管理员")


def update_last_login(username: str) -> bool:
    name = str(username or "").strip()
    if not name:
        return False
    engine = security_postgres_engine()
    if engine is None:
        user = _MEMORY_USERS.get(name)
        if not user:
            return False
        user["last_login_at"] = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
        return True
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET last_login_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE username = :username"),
                {"username": name},
            )
        return True
    except Exception:
        return False


def update_password(username: str, password_hash: str) -> bool:
    name = str(username or "").strip()
    if not name:
        return False
    engine = security_postgres_engine()
    if engine is None:
        user = _MEMORY_USERS.get(name)
        if not user:
            return False
        user["password_hash"] = password_hash
        user["updated_at"] = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
        return True
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET password_hash = :password_hash, updated_at = CURRENT_TIMESTAMP WHERE username = :username"),
                {"username": name, "password_hash": password_hash},
            )
        return True
    except Exception:
        return False
