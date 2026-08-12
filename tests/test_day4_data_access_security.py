from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.app.core.config import SecurityConfigurationError, get_settings, reset_settings_cache
from backend.app.data_registry import DATASET_REGISTRY
from backend.app.main import app


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_registry_is_static_complete_and_excludes_sensitive_objects():
    assert len(DATASET_REGISTRY) == 11
    forbidden = {"users", "roles", "user_roles", "audit_logs", "task_runs", "alembic_version"}
    assert forbidden.isdisjoint({spec.object_name for spec in DATASET_REGISTRY.values()})
    assert all(spec.dataset_id == key for key, spec in DATASET_REGISTRY.items())


def test_registry_public_contract_excludes_physical_names_and_sensitive_fields():
    forbidden_tokens = {"password", "secret", "token", "raw_json", "source_file", "payload_json"}
    for spec in DATASET_REGISTRY.values():
        public = spec.public_dict()
        assert "object_name" not in public
        assert "table_name" not in public
        for field in public["fields"]:
            assert "column_name" not in field
            assert not any(token in field["field_id"] for token in forbidden_tokens)


def test_arbitrary_sql_route_is_terminally_gone_for_all_payloads():
    for sql_text in (
        "SELECT 1",
        "SELECT * FROM users",
        "WITH q AS (SELECT 1) SELECT * FROM q",
        "SELECT pg_read_file('postgresql.conf')",
    ):
        response = client.post("/api/data/sql/query", json={"sql": sql_text})
        assert response.status_code == 410
        assert response.json()["detail"]["code"] == "arbitrary_sql_disabled"


def test_dynamic_database_object_routes_are_not_registered():
    assert client.get("/api/data/tables").status_code == 404
    assert client.get("/api/data/tables/users/rows").status_code == 404
    assert client.get("/api/data/tables/audit_logs/export").status_code == 404


def test_unregistered_dataset_and_field_fail_closed():
    assert client.get("/api/data/datasets/users/rows").status_code == 404
    assert client.get("/api/data/fields?dataset_id=audit_logs").status_code == 404
    response = client.get(
        "/api/data/datasets/market_price_history/rows?filter_field=raw_json&filter_value=x"
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "filter_field_not_allowed"


def test_query_enums_and_pagination_are_server_bounded():
    assert client.get("/api/data/datasets/market_price_history/rows?page_size=101").status_code == 422
    assert client.get("/api/data/datasets/market_price_history/rows?filter_operator=union").status_code == 422
    assert client.get("/api/data/datasets/market_price_history/rows?sort=raw_json").status_code == 400


def test_injection_text_is_bound_as_data_not_executed():
    response = client.get(
        "/api/data/datasets/market_price_history/rows",
        params={"search": "%' OR 1=1 --", "page_size": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["search_applied"] is True
    assert payload["records"] == []


def test_frontend_has_no_free_sql_or_physical_table_browser_client():
    source = "\n".join(
        [
            _read("frontend/src/api.ts"),
            _read("frontend/src/pages/data/DataCenterPage.tsx"),
            _read("frontend/src/components/data/DataCenterDesign.tsx"),
        ]
    )
    assert "readOnlySql" not in source
    assert "databaseTableRows" not in source
    assert "/api/data/tables" not in source
    assert "/api/data/datasets" in source
    assert "dataset_id" in source


def test_migrations_and_runtime_connections_are_explicitly_separated():
    migration = _read("migrations/env.py")
    settings = _read("backend/app/core/config.py")
    compose = _read("docker-compose.yml")
    assert "settings.migration_database_url" in migration
    assert "SECURITY_DATABASE_URL" in settings
    assert "database_bootstrap:" in compose
    assert "MIGRATION_DATABASE_URL:" in compose
    assert "AUTO_MIGRATE: 0" in compose
    assert "beta10d_app_login" in compose


def test_production_runtime_identity_cannot_fall_back_without_security_identity(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "day4-unit-test-jwt-secret-0123456789abcdef")
    monkeypatch.setenv("ADMIN_INITIALIZED", "1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://day4_runtime_test:unit-test-only@127.0.0.1:1/day4_test",
    )
    monkeypatch.delenv("SECURITY_DATABASE_URL", raising=False)
    reset_settings_cache()
    try:
        with pytest.raises(SecurityConfigurationError, match="SECURITY_DATABASE_URL"):
            get_settings()
    finally:
        reset_settings_cache()


def test_role_manifest_never_grants_all_tables_or_ddl():
    script = _read("scripts/day4_apply_database_security.py")
    assert "GRANT ALL" not in script.upper()
    assert "ON ALL TABLES" not in script.upper()
    assert "NOSUPERUSER" in script
    assert "NOCREATEDB" in script
    assert "NOCREATEROLE" in script
    assert "NOREPLICATION" in script
    assert "NOBYPASSRLS" in script
    assert '"users"' in script and '"audit_logs"' in script


def test_role_manifest_covers_runtime_rag_memory_and_chatbi_tables():
    from scripts.day4_apply_database_security import (
        BUSINESS_READ_ONLY_TABLES,
        BUSINESS_TABLES,
        DELETE_TABLES,
    )

    assert {
        "kb_document_versions",
        "kb_rag_audit_events",
        "kb_release_items",
        "kb_releases",
        "chatbi_dimension_catalog",
        "chatbi_join_catalog",
        "chatbi_metric_catalog",
    }.issubset(BUSINESS_READ_ONLY_TABLES)
    assert {
        "ai_memory_records",
        "ai_memory_versions",
        "ai_memory_relations",
        "ai_memory_usage",
        "ai_memory_outbox",
        "ai_memory_admissions",
        "ai_memory_state_transitions",
        "ai_memory_legal_holds",
        "ai_memory_deletion_jobs",
        "ai_memory_deletion_proofs",
        "chatbi_analysis_plans",
    }.issubset(BUSINESS_TABLES)
    assert {
        "ai_chat_sessions",
        "ai_chat_messages",
        "ai_conversation_state",
        "ai_tool_call_logs",
        "ai_chat_feedback",
        "ai_answer_feedback",
        "ai_traces",
    }.issubset(DELETE_TABLES)


def test_internal_dynamic_object_helpers_are_allowlisted():
    from backend.app.ai_assistant.tools.tariff_tools import _read_table
    from backend.app.repositories.market_data_repository import load_table_rows, table_exists

    assert table_exists("users") is False
    assert load_table_rows("users", limit=1) == []
    assert load_table_rows("raw_market", limit=1, order_by="password_hash") == []
    assert load_table_rows("raw_market", limit=1, where_sql="1=1; SELECT * FROM users") == []
    frame, source = _read_table("users", "users.csv")
    assert frame.empty
    assert source == "unregistered_dataset"
