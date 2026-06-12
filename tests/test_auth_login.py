from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.auth.password import hash_password
from backend.app.core.config import reset_settings_cache
from backend.app.db.session import reset_db_cache
from backend.app.main import app
from backend.app.repositories import audit_repository, user_repository
from backend.app.repositories.audit_repository import clear_memory_audit_logs, list_audit_logs
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


def _create_user(username: str, role: str, password: str = "Password123!") -> None:
    create_user(
        username=username,
        password_hash=hash_password(password),
        email=f"{username}@example.com",
        display_name=username,
        role=role,
        is_active=True,
    )


def test_login_success_returns_token_and_me_works():
    _create_user("admin1", "admin")
    response = client.post("/api/auth/login", json={"username": "admin1", "password": "Password123!"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["role"] == "admin"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "admin1"


def test_login_failure_writes_audit_without_password_or_token():
    _create_user("viewer1", "viewer")
    response = client.post("/api/auth/login", json={"username": "viewer1", "password": "wrong-password"})
    assert response.status_code == 401
    logs = list_audit_logs(action="auth.login_failed")
    assert logs
    serialized = json.dumps(logs, ensure_ascii=False)
    assert "wrong-password" not in serialized
    assert "Authorization" not in serialized
    assert "token" not in serialized.lower()


def test_protected_endpoint_requires_token_when_auth_required():
    response = client.get("/api/security/me")
    assert response.status_code == 401


def test_header_fallback_is_disabled_when_auth_required():
    response = client.get("/api/security/me", headers={"X-User": "viewer1", "X-Role": "viewer"})
    assert response.status_code == 401
