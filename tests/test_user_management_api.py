from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.auth.password import hash_password, verify_password
from backend.app.core.config import reset_settings_cache
from backend.app.db.session import reset_db_cache
from backend.app.main import app
from backend.app.repositories import audit_repository, user_repository
from backend.app.repositories.audit_repository import clear_memory_audit_logs
from backend.app.repositories.user_repository import clear_memory_users, create_user, get_user_by_username


client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "unit_test_jwt_secret")
    monkeypatch.setenv("DATABASE_URL", "")
    reset_settings_cache()
    reset_db_cache()
    monkeypatch.setattr(user_repository, "postgres_engine", lambda: None)
    monkeypatch.setattr(audit_repository, "postgres_engine", lambda: None)
    clear_memory_users()
    clear_memory_audit_logs()
    yield
    clear_memory_users()
    clear_memory_audit_logs()
    reset_settings_cache()
    reset_db_cache()


def _create_user(
    username: str,
    role: str,
    password: str = "Password123!",
    *,
    tenant_id: str = "default",
    workspace_id: str = "default",
):
    return create_user(
        username=username,
        password_hash=hash_password(password),
        display_name=username,
        role=role,
        is_active=True,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )


def _token(username: str, role: str) -> str:
    _create_user(username, role)
    response = client.post("/api/auth/login", json={"username": username, "password": "Password123!"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_admin_can_list_and_create_user_without_password_hash_in_response():
    token = _token("admin1", "admin")
    response = client.post(
        "/api/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "viewer1", "password": "ViewerPass123!", "role": "viewer", "email": "viewer1@example.com"},
    )
    assert response.status_code == 201
    payload = response.json()["user"]
    assert payload["username"] == "viewer1"
    assert "password_hash" not in payload

    stored = get_user_by_username("viewer1")
    assert stored
    assert stored["password_hash"] != "ViewerPass123!"
    assert verify_password("ViewerPass123!", stored["password_hash"])

    users = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert users.status_code == 200
    assert users.json()["total"] >= 2
    assert "password_hash" not in str(users.json())


def test_duplicate_username_returns_conflict():
    token = _token("admin1", "admin")
    _create_user("viewer1", "viewer")
    response = client.post(
        "/api/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "viewer1", "password": "ViewerPass123!", "role": "viewer"},
    )
    assert response.status_code == 409


def test_admin_updates_role_and_resets_password():
    token = _token("admin1", "admin")
    target = _create_user("viewer1", "viewer", password="OldPassword123!")
    user_id = target["user_id"]

    role_response = client.patch(
        f"/api/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "analyst", "display_name": "分析员一号"},
    )
    assert role_response.status_code == 200
    assert role_response.json()["user"]["role"] == "analyst"

    reset_response = client.post(
        f"/api/users/{user_id}/reset-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_password": "NewPassword123!"},
    )
    assert reset_response.status_code == 200
    assert client.post("/api/auth/login", json={"username": "viewer1", "password": "OldPassword123!"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "viewer1", "password": "NewPassword123!"}).status_code == 200


def test_disabled_user_cannot_login():
    token = _token("admin1", "admin")
    target = _create_user("viewer1", "viewer")
    response = client.delete(f"/api/users/{target['user_id']}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"]["is_active"] is False
    assert client.post("/api/auth/login", json={"username": "viewer1", "password": "Password123!"}).status_code == 401


def test_cannot_disable_or_demote_last_admin():
    token = _token("admin1", "admin")
    admin = get_user_by_username("admin1")
    assert admin
    disable = client.delete(f"/api/users/{admin['user_id']}", headers={"Authorization": f"Bearer {token}"})
    assert disable.status_code == 400
    demote = client.patch(
        f"/api/users/{admin['user_id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "viewer"},
    )
    assert demote.status_code == 400


def test_admin_user_management_is_tenant_and_workspace_scoped():
    admin_a = _create_user("admin_a", "admin", tenant_id="tenant_a", workspace_id="workspace_a")
    admin_b = _create_user("admin_b", "admin", tenant_id="tenant_b", workspace_id="workspace_b")
    target_a = _create_user("analyst_a", "analyst", tenant_id="tenant_a", workspace_id="workspace_a")
    _create_user("viewer_b", "viewer", tenant_id="tenant_b", workspace_id="workspace_b")

    login_b = client.post(
        "/api/auth/login",
        json={"username": "admin_b", "password": "Password123!"},
    )
    assert login_b.status_code == 200
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    users = client.get("/api/users", headers=headers_b)
    settings_users = client.get("/api/settings/users", headers=headers_b)
    assert users.status_code == settings_users.status_code == 200
    assert {item["username"] for item in users.json()["items"]} == {"admin_b", "viewer_b"}
    assert {item["username"] for item in settings_users.json()["items"]} == {"admin_b", "viewer_b"}
    assert all(item["tenant_id"] == "tenant_b" for item in users.json()["items"])
    assert all(item["workspace_id"] == "workspace_b" for item in users.json()["items"])

    denied_update = client.patch(
        f"/api/users/{target_a['user_id']}",
        headers=headers_b,
        json={"role": "viewer"},
    )
    denied_reset = client.post(
        f"/api/settings/users/{target_a['user_id']}/reset-password",
        headers=headers_b,
        json={"new_password": "ChangedPassword123!"},
    )
    assert denied_update.status_code == 404
    assert denied_reset.status_code == 404

    created_b = client.post(
        "/api/users",
        headers=headers_b,
        json={"username": "new_b", "password": "NewTenantUser123!", "role": "viewer"},
    )
    assert created_b.status_code == 201
    assert created_b.json()["user"]["tenant_id"] == "tenant_b"
    assert created_b.json()["user"]["workspace_id"] == "workspace_b"
    assert admin_a["tenant_id"] == "tenant_a"
    assert admin_b["tenant_id"] == "tenant_b"
