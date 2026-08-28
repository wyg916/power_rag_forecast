from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.app.auth.jwt import decode_access_token
from backend.app.auth.password import hash_password
from backend.app.core.config import reset_settings_cache
from backend.app.db.session import reset_db_cache
from backend.app.main import app
from backend.app.repositories import audit_repository, settings_repository, user_repository
from backend.app.repositories.audit_repository import clear_memory_audit_logs
from backend.app.repositories.settings_repository import clear_memory_settings
from backend.app.repositories.user_repository import clear_memory_users, create_user
from backend.app.services import settings_center_service


client = TestClient(app)


@pytest.fixture(autouse=True)
def _settings_center_env(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", "settings_center_test_jwt_secret")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    reset_settings_cache()
    reset_db_cache()
    monkeypatch.setattr(settings_repository, "postgres_engine", lambda: None)
    monkeypatch.setattr(user_repository, "postgres_engine", lambda: None)
    monkeypatch.setattr(audit_repository, "postgres_engine", lambda: None)
    clear_memory_settings()
    clear_memory_users()
    clear_memory_audit_logs()
    create_user(
        username="admin",
        password_hash=hash_password("AdminPass123!"),
        display_name="admin",
        role="admin",
        is_active=True,
    )
    yield
    clear_memory_settings()
    clear_memory_users()
    clear_memory_audit_logs()
    reset_settings_cache()
    reset_db_cache()


def test_settings_status_and_runtime_config_endpoints():
    overview = client.get("/api/settings/status/overview")
    assert overview.status_code == 200
    assert "healthy_services" in overview.json()

    summary = client.get("/api/settings/status/summary")
    assert summary.status_code == 200
    assert isinstance(summary.json()["items"], list)

    details = client.get("/api/settings/status/health-details")
    assert details.status_code == 200
    assert isinstance(details.json()["items"], list)

    runtime = client.get("/api/settings/runtime-config")
    assert runtime.status_code == 200
    assert "data_refresh_interval_minutes" in runtime.json()["values"]

    update = client.put("/api/settings/runtime-config", json={"values": {"data_refresh_interval_minutes": 9}})
    assert update.status_code == 200
    assert update.json()["values"]["data_refresh_interval_minutes"] == 9

    records = client.get("/api/settings/status/check-records?limit=5")
    assert records.status_code == 200
    assert isinstance(records.json()["items"], list)
    assert records.json()["items"][0]["status"] == "unavailable"


def test_settings_get_endpoints_merge_defaults_without_writing_storage():
    assert settings_repository._RUNTIME_MEMORY == {}
    assert settings_repository._API_CONFIG_MEMORY == {}

    assert client.get("/api/settings/runtime-config").status_code == 200
    assert client.get("/api/settings/security-policy").status_code == 200
    assert client.get("/api/settings/roles/permissions").status_code == 200
    interfaces = client.get("/api/settings/interfaces/configs")

    assert interfaces.status_code == 200
    keys = {item["interface_key"] for item in interfaces.json()["items"]}
    assert {"llm_kimi", "llm_mimo", "llm_deepseek"} <= keys
    assert settings_repository._RUNTIME_MEMORY == {}
    assert settings_repository._API_CONFIG_MEMORY == {}


def test_health_snapshot_store_uses_application_runtime_identity(monkeypatch):
    application_engine = object()
    monkeypatch.setattr(settings_repository, "_application_postgres_engine", lambda: application_engine)
    monkeypatch.setattr(
        settings_repository,
        "postgres_engine",
        lambda: (_ for _ in ()).throw(AssertionError("security identity must not serve health snapshots")),
    )

    assert settings_repository.health_postgres_engine() is application_engine


def test_health_snapshot_queries_fail_closed_without_database_or_permission(monkeypatch):
    clear_memory_settings()
    monkeypatch.setattr(settings_repository, "health_postgres_engine", lambda: None)
    missing_dsn = settings_repository.health_check_records(limit=5)
    assert missing_dsn[0]["status"] == "unavailable"
    assert missing_dsn[0]["extra_json"]["reason"] == "database_not_configured_or_unreachable"

    class PermissionDeniedEngine:
        def connect(self):
            raise SQLAlchemyError("permission denied")

    monkeypatch.setattr(settings_repository, "health_postgres_engine", lambda: PermissionDeniedEngine())
    denied = settings_repository.latest_health_snapshots(limit=5)
    assert denied[0]["status"] == "unavailable"
    assert denied[0]["extra_json"]["reason"] == "query_unavailable"


def test_runtime_health_get_path_does_not_persist_snapshots(monkeypatch):
    clear_memory_settings()
    monkeypatch.setattr(
        settings_center_service,
        "database_runtime_status",
        lambda: {"active": "postgresql", "available": True, "message": "available"},
    )
    monkeypatch.setattr(
        settings_center_service,
        "task_runtime_health",
        lambda: {"redis": {"ok": True, "status": "ok"}, "celery": {"ok": True, "worker_count": 1}},
    )
    monkeypatch.setattr(settings_center_service, "rag_health", lambda: {"ok": True, "status": "normal"})
    monkeypatch.setattr(settings_center_service, "get_local_llm_status", lambda: {"available": False})

    rows = settings_center_service.collect_runtime_health_rows()

    assert rows
    assert settings_repository._HEALTH_MEMORY == []


def test_settings_user_role_security_and_audit_endpoints():
    created = client.post(
        "/api/settings/users",
        json={
            "username": "zhangsan",
            "display_name": "张三",
            "email": "zhangsan@example.com",
            "password": "Password123!",
            "role": "analyst",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["user"]["user_id"]

    users = client.get("/api/settings/users?keyword=zhangsan")
    assert users.status_code == 200
    assert users.json()["total"] == 1

    assign = client.post(f"/api/settings/users/{user_id}/assign-role", json={"role": "developer"})
    assert assign.status_code == 200
    assert assign.json()["user"]["role"] == "developer"

    reset = client.post(f"/api/settings/users/{user_id}/reset-password", json={"new_password": "NewPassword123!"})
    assert reset.status_code == 200
    assert "NewPassword123!" not in str(client.get("/api/settings/audit-logs").json())

    roles = client.get("/api/settings/roles/permissions")
    assert roles.status_code == 200
    assert any(row["role_id"] == "admin" for row in roles.json()["roles"])
    assert any(row["role_id"] == "admin" and row["admin"] for row in roles.json()["matrix"])

    role_update = client.put(
        "/api/settings/roles/permissions",
        json={"roles": [{"role_id": "viewer", "role_name": "查看者", "permissions": ["dashboard:read", "audit:read"]}]},
    )
    assert role_update.status_code == 200
    viewer = next(row for row in role_update.json()["roles"] if row["role_id"] == "viewer")
    assert viewer["permissions"] == ["audit:read", "dashboard:read"]

    security = client.put("/api/settings/security-policy", json={"values": {"password_min_length": 14}})
    assert security.status_code == 200
    assert security.json()["values"]["password_min_length"] == 14
    assert client.put("/api/settings/security-policy", json={"values": {"password_min_length": 7}}).status_code == 400
    assert client.put("/api/settings/security-policy", json={"values": {"two_factor_enabled": True}}).status_code == 400

    overview = client.get("/api/settings/users/overview")
    assert overview.status_code == 200
    assert overview.json()["user_total"] >= 2


def test_settings_interface_configs_test_and_logs():
    configs = client.get("/api/settings/interfaces/configs")
    assert configs.status_code == 200
    assert configs.json()["total"] >= 1
    assert "AdminPass123!" not in str(configs.json())

    web_test = client.post("/api/settings/interfaces/web/test")
    assert web_test.status_code == 200
    assert web_test.json()["ok"] is True

    logs = client.get("/api/settings/interfaces/test-logs")
    assert logs.status_code == 200
    assert logs.json()["total"] >= 1
    assert logs.json()["items"][0]["interface_key"] == "web"

    overview = client.get("/api/settings/interfaces/overview")
    assert overview.status_code == 200
    assert overview.json()["interface_total"] >= 1

    all_tests = client.post("/api/settings/interfaces/test-all")
    assert all_tests.status_code == 200
    assert "items" in all_tests.json()


def test_remote_provider_interface_probe_uses_real_adapter_contract_without_exposing_content(monkeypatch):
    class FakeProvider:
        name = "kimi"
        display_name = "Kimi K2.6"
        default_model = "kimi-k2.6"
        available = True

        def complete(self, _messages, **_options):
            return type("Result", (), {"content": "sensitive answer", "model": self.default_model, "finish_reason": "stop"})()

    monkeypatch.setitem(settings_center_service.PROVIDER_FACTORIES, "llm_kimi", FakeProvider)
    response = client.post("/api/settings/interfaces/llm_kimi/test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["extra"]["provider"] == "kimi"
    assert "sensitive answer" not in str(payload)

    refreshed = client.get("/api/settings/interfaces?page_size=100")
    kimi = next(item for item in refreshed.json()["items"] if item["interface_key"] == "llm_kimi")
    assert kimi["status"] == "normal"
    assert kimi["success_rate"] == 100
    assert kimi["persisted"] is True


def test_login_lock_threshold_and_session_timeout_policy_are_enforced():
    create_user(
        username="locked1", password_hash=hash_password("Password123!"),
        display_name="locked1", role="viewer", is_active=True,
    )
    settings_repository.upsert_runtime_config(
        "login_failed_lock_count", 3, value_type="integer", category="security_policy"
    )
    settings_repository.upsert_runtime_config(
        "session_timeout_minutes", 7, value_type="integer", category="security_policy"
    )

    assert client.post("/api/auth/login", json={"username": "locked1", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "locked1", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "locked1", "password": "wrong"}).status_code == 423
    assert client.post("/api/auth/login", json={"username": "locked1", "password": "Password123!"}).status_code == 423

    login = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass123!"})
    assert login.status_code == 200
    token = decode_access_token(login.json()["access_token"])
    assert token["exp"] - token["iat"] == 7 * 60


def test_login_uses_persisted_role_configuration():
    settings_repository.upsert_role_permissions(
        "viewer", ["dashboard:read", "assistant:use"], role_name="查看者"
    )
    create_user(
        username="configured1", password_hash=hash_password("Password123!"),
        display_name="configured1", role="viewer", is_active=True,
    )

    response = client.post("/api/auth/login", json={"username": "configured1", "password": "Password123!"})

    assert response.status_code == 200
    assert response.json()["user"]["permissions"] == ["assistant:use", "dashboard:read"]
