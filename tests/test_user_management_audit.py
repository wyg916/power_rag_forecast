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


def _admin_token() -> str:
    create_user(username="admin1", password_hash=hash_password("Password123!"), display_name="admin1", role="admin", is_active=True)
    response = client.post("/api/auth/login", json={"username": "admin1", "password": "Password123!"})
    return response.json()["access_token"]


def test_user_management_actions_write_masked_audit_logs():
    token = _admin_token()
    create = client.post(
        "/api/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "viewer1", "password": "SecretPassword123!", "role": "viewer"},
    )
    user_id = create.json()["user"]["user_id"]
    client.patch(f"/api/users/{user_id}", headers={"Authorization": f"Bearer {token}"}, json={"role": "analyst"})
    client.post(f"/api/users/{user_id}/reset-password", headers={"Authorization": f"Bearer {token}"}, json={"new_password": "NewSecret123!"})
    client.delete(f"/api/users/{user_id}", headers={"Authorization": f"Bearer {token}"})

    logs = list_audit_logs()
    actions = {row["action"] for row in logs}
    assert {"user.create", "user.role_update", "user.password_reset", "user.disable"}.issubset(actions)
    serialized = json.dumps(logs, ensure_ascii=False)
    assert "SecretPassword123!" not in serialized
    assert "NewSecret123!" not in serialized
    assert "password_hash" not in serialized
    assert "Authorization" not in serialized
    assert "token" not in serialized.lower()
