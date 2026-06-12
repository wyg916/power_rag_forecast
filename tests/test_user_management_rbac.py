from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.auth.password import hash_password
from backend.app.core.config import reset_settings_cache
from backend.app.db.session import reset_db_cache
from backend.app.main import app
from backend.app.repositories import audit_repository, user_repository
from backend.app.repositories.audit_repository import clear_memory_audit_logs
from backend.app.repositories.user_repository import clear_memory_users, create_user


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


def _token(username: str, role: str) -> str:
    create_user(username=username, password_hash=hash_password("Password123!"), display_name=username, role=role, is_active=True)
    response = client.post("/api/auth/login", json={"username": username, "password": "Password123!"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_viewer_and_analyst_cannot_list_users():
    viewer = _token("viewer1", "viewer")
    analyst = _token("analyst1", "analyst")
    assert client.get("/api/users", headers={"Authorization": f"Bearer {viewer}"}).status_code == 403
    assert client.get("/api/users", headers={"Authorization": f"Bearer {analyst}"}).status_code == 403


def test_developer_can_read_but_cannot_write_users():
    token = _token("dev1", "developer")
    assert client.get("/api/users", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    response = client.post(
        "/api/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "viewer1", "password": "Password123!", "role": "viewer"},
    )
    assert response.status_code == 403
