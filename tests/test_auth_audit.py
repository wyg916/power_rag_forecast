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


def test_login_success_and_logout_are_audited_without_secrets():
    create_user(username="admin1", password_hash=hash_password("Password123!"), display_name="admin1", role="admin")
    login = client.post("/api/auth/login", json={"username": "admin1", "password": "Password123!"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}, json={})
    assert logout.status_code == 200

    logs = list_audit_logs()
    actions = {row["action"] for row in logs}
    assert "auth.login_success" in actions
    assert "auth.logout" in actions
    serialized = json.dumps(logs, ensure_ascii=False)
    assert "Password123!" not in serialized
    assert token not in serialized
    assert "Authorization" not in serialized


def test_password_change_is_audited_and_masks_plaintext():
    create_user(username="analyst1", password_hash=hash_password("Password123!"), display_name="analyst1", role="analyst")
    login = client.post("/api/auth/login", json={"username": "analyst1", "password": "Password123!"})
    token = login.json()["access_token"]
    response = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "Password123!", "new_password": "NewPassword123!"},
    )
    assert response.status_code == 200
    serialized = json.dumps(list_audit_logs(action="auth.password_change"), ensure_ascii=False)
    assert "Password123!" not in serialized
    assert "NewPassword123!" not in serialized
