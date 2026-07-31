from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import observability
from backend.app.api.v1.endpoints import system as system_endpoint
from backend.app.api.v1.endpoints.assistant import _format_messages_for_export, _stream_event
from backend.app.auth.jwt import JWTError, create_access_token, decode_access_token
from backend.app.core import config as config_module
from backend.app.core.config import SecurityConfigurationError, get_settings, reset_settings_cache
from backend.app.core.security import CurrentUser, require_permission
from backend.app.main import app, create_app, sanitized_http_exception_handler


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)
SECURITY_ENV_KEYS = ("APP_ENV", "ENV", "AUTH_REQUIRED", "JWT_SECRET_KEY", "JWT_ALGORITHM", "ADMIN_INITIALIZED")
STRONG_TEST_SECRET = "t004-isolated-test-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def _isolated_security_env(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    for key in SECURITY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def _production_env(monkeypatch, *, secret: str | None = STRONG_TEST_SECRET, auth: str | None = "1", admin: str | None = "1") -> None:
    monkeypatch.setenv("APP_ENV", "production")
    for name, value in (("JWT_SECRET_KEY", secret), ("AUTH_REQUIRED", auth), ("ADMIN_INITIALIZED", admin)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    reset_settings_cache()


@pytest.mark.parametrize(
    "secret",
    [None, "", "change_me", "change_me_dev_jwt_secret", "placeholder-secret-value-that-is-long-enough", "${JWT_SECRET_KEY}"],
)
def test_production_rejects_missing_empty_or_weak_jwt_secret(monkeypatch, secret):
    _production_env(monkeypatch, secret=secret)
    with pytest.raises(SecurityConfigurationError, match="JWT_SECRET_KEY"):
        create_app()


def test_production_rejects_disabled_auth(monkeypatch):
    _production_env(monkeypatch, auth="0")
    with pytest.raises(SecurityConfigurationError, match="AUTH_REQUIRED"):
        get_settings()


def test_production_rejects_missing_admin_initialization(monkeypatch):
    _production_env(monkeypatch, admin=None)
    with pytest.raises(SecurityConfigurationError, match="ADMIN_INITIALIZED"):
        create_app()


def test_production_defaults_auth_on_but_development_and_test_default_off(monkeypatch):
    _production_env(monkeypatch, auth=None)
    assert get_settings().auth_required is True
    for app_env in ("development", "test"):
        monkeypatch.setenv("APP_ENV", app_env)
        monkeypatch.delenv("AUTH_REQUIRED", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.delenv("ADMIN_INITIALIZED", raising=False)
        reset_settings_cache()
        settings = get_settings()
        assert settings.app_env == app_env
        assert settings.auth_required is False


def test_invalid_and_expired_tokens_are_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", STRONG_TEST_SECRET)
    reset_settings_cache()
    token = create_access_token(subject="alice", user_id="u1", role="viewer", extra={"exp": int(time.time()) - 1})
    with pytest.raises(JWTError, match="expired"):
        decode_access_token(token)
    with pytest.raises(JWTError):
        decode_access_token(token[:-2] + "xx")


def test_protected_api_returns_401_without_token(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", STRONG_TEST_SECRET)
    reset_settings_cache()
    response = client.get("/api/security/me")
    assert response.status_code == 401


def test_permission_dependency_returns_403_and_allows_admin():
    from starlette.requests import Request

    request = Request({"type": "http", "headers": []})
    dependency = require_permission("security:read")
    viewer = CurrentUser(user_id="viewer", username="viewer", role="viewer", permissions=[], auth_mode="test")
    with pytest.raises(HTTPException) as denied:
        dependency(request, viewer)
    assert denied.value.status_code == 403

    admin = CurrentUser(user_id="admin", username="admin", role="admin", permissions=["*"], auth_mode="test")
    assert dependency(request, admin) is admin


def test_api_sse_export_and_log_messages_are_redacted(monkeypatch):
    secret = "t004-super-secret-value"
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature123"
    db_url = "postgresql://user:db-password@localhost/db"
    exc = HTTPException(status_code=400, detail=f"JWT_SECRET_KEY={secret} Authorization: Bearer {token} {db_url}")
    response = asyncio.run(sanitized_http_exception_handler(None, exc))
    body = response.body.decode("utf-8")
    assert secret not in body and token not in body and "db-password" not in body

    frame = _stream_event("error", {"message": f"password={secret} Bearer {token}"})
    rows = _format_messages_for_export([{"role": "user", "content": f"api_key={secret} {db_url}"}])
    assert secret not in frame and token not in frame
    assert secret not in json.dumps(rows, ensure_ascii=False) and "db-password" not in json.dumps(rows, ensure_ascii=False)

    captured: dict[str, object] = {}

    class _Logger:
        def warning(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(observability, "configure_app_logging", lambda: None)
    monkeypatch.setattr(observability, "app_logger", lambda: _Logger())
    message = observability.log_suppressed_exception("t004", RuntimeError(f"password={secret} Bearer {token}"))
    assert secret not in message and token not in message
    assert captured["kwargs"]["exc_info"] is False


def test_health_and_isolated_database_health_do_not_regress(monkeypatch):
    assert client.get("/api/health").status_code == 200
    monkeypatch.setattr(system_endpoint, "database_runtime_status", lambda: {"active": "postgresql", "message": "isolated-test"})
    response = client.get("/api/db/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "active": "postgresql", "message": "isolated-test"}


def test_frontend_and_deployment_auth_contracts_are_fail_closed():
    context = (ROOT / "frontend/src/context/AuthContext.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    auth_api = (ROOT / "frontend/src/services/authApi.ts").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    enterprise_compose = (ROOT / "docker-compose.enterprise.yml").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "VITE_AUTH_REQUIRED ?? '1'" in context
    assert "setLoginRequested(authRequired)" in context
    assert "sanitizeErrorMessage" in api
    assert "登录响应缺少访问令牌或用户信息" in auth_api
    jwt_lines = [line for line in compose.splitlines() if "JWT_SECRET_KEY:" in line]
    admin_lines = [line for line in compose.splitlines() if "ADMIN_INITIALIZED:" in line]
    assert jwt_lines and all(":?JWT_SECRET_KEY is required for production" in line for line in jwt_lines)
    assert admin_lines and all(":?ADMIN_INITIALIZED=1 is required after admin bootstrap" in line for line in admin_lines)
    assert "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}" in compose
    assert "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}" in enterprise_compose
    assert "AUTH_REQUIRED: ${AUTH_REQUIRED:-0}" not in enterprise_compose
    assert "POSTGRES_PASSWORD:-postgres" not in enterprise_compose
    assert "JWT_SECRET_KEY=change_me" not in example


def test_env_docker_requires_external_production_secrets(monkeypatch):
    values: dict[str, str] = {}
    for raw_line in (ROOT / ".env.docker.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    assert values.get("APP_ENV") == "production"
    assert values.get("AUTH_REQUIRED") == "1"
    assert values.get("ADMIN_INITIALIZED") == "1"
    assert values.get("JWT_SECRET_KEY", "").startswith("replace_with_")
    assert values.get("POSTGRES_PASSWORD", "").startswith("replace_with_")
    assert not values.get("ADMIN_PASSWORD")
    assert values.get("RAG_ENABLED") == "0"
    assert values.get("RAG_EMBEDDING_ALLOW_FALLBACK") == "0"
    assert values.get("RAG_FILE_FALLBACK_ENABLED") == "0"

    monkeypatch.setenv("APP_ENV", values["APP_ENV"])
    monkeypatch.setenv("AUTH_REQUIRED", values["AUTH_REQUIRED"])
    monkeypatch.setenv("JWT_SECRET_KEY", values["JWT_SECRET_KEY"])
    monkeypatch.setenv("ADMIN_INITIALIZED", values["ADMIN_INITIALIZED"])
    reset_settings_cache()
    with pytest.raises(SecurityConfigurationError, match="JWT_SECRET_KEY"):
        create_app()


def test_day2_preflight_static_gates_pass():
    from scripts.day2_repro_preflight import _config_checks, _migration_checks

    _, config_failures = _config_checks(ROOT / ".env.docker.example")
    migration_result, migration_failures = _migration_checks()

    assert config_failures == []
    assert migration_failures == []
    assert migration_result["files_scanned"] == 16

    env_py = (ROOT / "migrations/env.py").read_text(encoding="utf-8")
    assert "ALEMBIC_TARGET_SCHEMA" in env_py
    assert "version_table_schema" in env_py
    assert "SET search_path" in env_py
    assert "context.run_migrations()" in env_py
