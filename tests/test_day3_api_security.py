from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.auth.jwt import create_access_token
from backend.app.core import security
from backend.app.core.api_security import (
    DEVELOPMENT_DOC_ROUTE_KEYS,
    MATRIX_PATH,
    PUBLIC_ROUTE_KEYS,
    ApiSecurityMiddleware,
    app_route_keys,
    load_route_policies,
    validate_app_route_coverage,
)
from backend.app.core.config import reset_settings_cache
from backend.app.core.security import CurrentUser, ROLE_PERMISSIONS, get_current_user
from backend.app.main import app, create_app
from scripts.day3_generate_permission_matrix import build_rows


pytestmark = pytest.mark.no_legacy_auth
STRONG_SECRET = "day3-unit-test-secret-0123456789abcdef"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _security_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", STRONG_SECRET)
    monkeypatch.delenv("ADMIN_INITIALIZED", raising=False)
    reset_settings_cache()
    load_route_policies.cache_clear()
    app.dependency_overrides.pop(get_current_user, None)
    yield
    app.dependency_overrides.pop(get_current_user, None)
    reset_settings_cache()
    load_route_policies.cache_clear()


def _matrix_rows() -> list[dict[str, str]]:
    with MATRIX_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _user(role: str) -> CurrentUser:
    permissions = sorted(ROLE_PERMISSIONS[role])
    return CurrentUser(
        user_id=f"{role}-id",
        username=role,
        role=role,
        permissions=permissions,
        auth_mode="dependency_override",
    )


def _probe_client(user: CurrentUser | None = None) -> TestClient:
    probe = FastAPI()

    @probe.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def allowed_probe(path: str) -> dict[str, str]:
        return {"path": path}

    probe.add_middleware(ApiSecurityMiddleware)
    if user is not None:
        probe.dependency_overrides[get_current_user] = lambda: user
    return TestClient(probe)


def test_permission_matrix_exactly_covers_runtime_routes_and_is_reproducible():
    rows = _matrix_rows()
    matrix_keys = {(row["Method"], row["Path"]) for row in rows}
    runtime_keys = app_route_keys(app)

    assert len(rows) == 196
    assert len({row["Path"] for row in rows}) == 184
    assert matrix_keys == runtime_keys
    assert rows == build_rows()
    validate_app_route_coverage(app)


def test_unclassified_new_route_fails_static_gate():
    probe = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @probe.get("/api/day3-unclassified")
    def unclassified() -> dict[str, bool]:
        return {"ok": True}

    with pytest.raises(RuntimeError, match="missing=.*day3-unclassified"):
        validate_app_route_coverage(probe)


def test_public_whitelist_and_all_protected_or_write_routes_are_explicit():
    rows = _matrix_rows()
    assert all("Route Name" in row and "Response Model" in row for row in rows)
    public = {(row["Method"], row["Path"]) for row in rows if row["Anonymous"] == "yes"}
    assert public == PUBLIC_ROUTE_KEYS
    for row in rows:
        if row["Anonymous"] == "no":
            assert row["Required Permission"]
            assert row["Target Guard"] == f"authenticated+permission:{row['Required Permission']}"
        if row["Write Operation"] == "yes" and row["Anonymous"] == "no":
            assert row["Required Permission"]
            assert row["Allowed Roles"] != "anonymous"


@pytest.mark.parametrize(
    ("role", "method", "path", "expected"),
    [
        ("viewer", "GET", "/api/dashboard/overview", 200),
        ("analyst", "GET", "/api/dashboard/overview", 200),
        ("viewer", "GET", "/api/forecast/latest", 200),
        ("viewer", "POST", "/api/forecast/run", 403),
        ("analyst", "POST", "/api/forecast/run", 200),
        ("viewer", "GET", "/api/reports/latest", 200),
        ("viewer", "POST", "/api/reports/generate", 403),
        ("analyst", "POST", "/api/reports/generate", 200),
        ("viewer", "GET", "/api/strategy/latest", 200),
        ("analyst", "POST", "/api/strategies/strategy-1/approve", 403),
        ("viewer", "POST", "/api/strategies/strategy-1/approve", 403),
        ("admin", "POST", "/api/strategies/strategy-1/approve", 200),
        ("viewer", "POST", "/api/models/center/activate", 403),
        ("analyst", "POST", "/api/models/center/activate", 403),
        ("admin", "POST", "/api/models/center/activate", 200),
        ("viewer", "POST", "/api/tasks/task-1/retry", 403),
        ("analyst", "POST", "/api/tasks/task-1/retry", 403),
        ("admin", "POST", "/api/tasks/task-1/retry", 200),
        ("viewer", "GET", "/api/users", 403),
        ("analyst", "GET", "/api/users", 403),
        ("admin", "GET", "/api/users", 200),
        ("viewer", "GET", "/api/audit/logs", 403),
        ("analyst", "GET", "/api/audit/logs", 403),
        ("admin", "GET", "/api/audit/logs", 200),
        ("viewer", "PUT", "/api/settings/runtime-config", 403),
        ("analyst", "PUT", "/api/settings/runtime-config", 403),
        ("admin", "PUT", "/api/settings/runtime-config", 200),
    ],
)
def test_role_permission_matrix(role, method, path, expected):
    response = _probe_client(_user(role)).request(method, path, json={})
    assert response.status_code == expected


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/dashboard/overview"),
        ("GET", "/api/forecast/latest"),
        ("GET", "/api/reports/latest"),
        ("GET", "/api/strategy/latest"),
        ("POST", "/api/ai/chat/stream"),
        ("GET", "/api/knowledge/documents"),
        ("GET", "/api/models/active"),
        ("GET", "/api/tasks"),
        ("GET", "/api/settings/config"),
        ("GET", "/api/users"),
        ("GET", "/api/data/datasets"),
    ],
)
def test_anonymous_users_cannot_access_business_domains(method, path):
    response = _probe_client().request(method, path, json={} if method != "GET" else None)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "缺少登录令牌"}


def test_401_contract_invalid_expired_incomplete_and_disabled_users(monkeypatch):
    client = TestClient(app)
    valid_record = {"user_id": "viewer-id", "username": "viewer", "role": "viewer", "is_active": True}
    monkeypatch.setattr(security, "get_user_by_username", lambda username: valid_record)
    expired = create_access_token(
        subject="viewer",
        user_id="viewer-id",
        role="viewer",
        permissions=[],
        extra={"exp": int(time.time()) - 1},
    )
    incomplete = create_access_token(subject="viewer", user_id="viewer-id", role="viewer", extra={"sub": ""})
    cases = ["broken-token", expired, incomplete]
    for token in cases:
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert set(response.json()) == {"detail"}
        assert "Traceback" not in response.text

    disabled = {**valid_record, "is_active": False}
    monkeypatch.setattr(security, "get_user_by_username", lambda username: disabled)
    token = create_access_token(subject="viewer", user_id="viewer-id", role="viewer", permissions=[])
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_empty_token_permissions_use_current_role_and_403_is_distinct(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_user_by_username",
        lambda username: {"user_id": "viewer-id", "username": username, "role": "viewer", "is_active": True},
    )
    token = create_access_token(subject="viewer", user_id="viewer-id", role="viewer", permissions=[])
    client = TestClient(app)
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    denied = client.post("/api/reports/generate", headers={"Authorization": f"Bearer {token}"}, json={})
    assert me.status_code == 200
    assert "report:generate" not in me.json()["user"]["permissions"]
    assert denied.status_code == 403
    assert "www-authenticate" not in denied.headers
    assert denied.json() == {"detail": "缺少权限：report:generate"}


def test_unknown_development_role_has_no_viewer_fallback(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    reset_settings_cache()
    client = TestClient(app)
    response = client.get(
        "/api/dashboard/overview",
        headers={"X-User": "unknown-role-user", "X-Role": "unknown-role"},
    )
    assert response.status_code == 403
    assert security._permissions_for_role("unknown-role") == []


def test_cors_headers_are_preserved_on_authentication_errors():
    response = TestClient(app).get(
        "/api/auth/me",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_download_stream_and_compatibility_aliases_have_no_bypass():
    rows = _matrix_rows()
    by_key = {(row["Method"], row["Path"]): row for row in rows}
    aliases = [
        ("/api/model/backtest/summary", "/api/models/backtest/summary"),
        ("/api/model/feature-schema", "/api/models/feature-schema"),
        ("/api/model/leakage-check", "/api/models/leakage-check"),
    ]
    for left, right in aliases:
        assert by_key[("GET", left)]["Required Permission"] == by_key[("GET", right)]["Required Permission"]
        assert "compatibility alias" in by_key[("GET", left)]["Notes"]
        assert "compatibility alias" in by_key[("GET", right)]["Notes"]

    anonymous = TestClient(app)
    for method, path in [
        ("GET", "/api/reports/missing/download"),
        ("POST", "/api/ai/chat/stream"),
        ("GET", "/api/model/feature-schema"),
        ("GET", "/api/models/feature-schema"),
    ]:
        assert anonymous.request(method, path, json={} if method == "POST" else None).status_code == 401

    analyst = _user("analyst")
    app.dependency_overrides[get_current_user] = lambda: analyst
    assert TestClient(app).get("/api/reports/missing/download").status_code == 404
    assert _probe_client(analyst).post("/api/ai/chat/stream", json={}).status_code == 200


def test_production_disables_documentation_routes(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", STRONG_SECRET)
    monkeypatch.setenv("ADMIN_INITIALIZED", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://runtime:placeholder@localhost:5432/postgres")
    monkeypatch.setenv("SECURITY_DATABASE_URL", "postgresql+psycopg://security:placeholder@localhost:5432/postgres")
    reset_settings_cache()
    production_app = create_app()
    validate_app_route_coverage(production_app)
    assert DEVELOPMENT_DOC_ROUTE_KEYS.isdisjoint(app_route_keys(production_app))
    client = TestClient(production_app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_frontend_auth_and_permission_contracts():
    auth_context = (ROOT / "frontend/src/context/AuthContext.tsx").read_text(encoding="utf-8")
    api_source = (ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    report_page = (ROOT / "frontend/src/pages/report/ReportCenterPage.tsx").read_text(encoding="utf-8")
    task_page = (ROOT / "frontend/src/pages/task/TaskCenterPage.tsx").read_text(encoding="utf-8")
    model_page = (ROOT / "frontend/src/pages/model/ModelCenterPage.tsx").read_text(encoding="utf-8")
    view_state = (ROOT / "frontend/src/services/viewState.ts").read_text(encoding="utf-8")

    assert "VITE_AUTH_REQUIRED ?? '1'" in auth_context
    assert "auth:unauthorized" in api_source
    assert "requestDownload(`/api/reports/${encodeURIComponent(reportId)}/download`)" in api_source
    assert "window.open(api.reportDownloadUrl" not in report_page
    assert "report:generate" in report_page and "report:review" in report_page
    assert "task:manage" in task_page
    assert "model:manage" in model_page
    assert "descriptor.status === 403" in view_state and "state: 'forbidden'" in view_state
