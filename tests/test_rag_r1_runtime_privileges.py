from pathlib import Path

import pytest

from scripts.rag_r1_runtime_privileges import (
    APPEND_TABLES,
    READ_ONLY_TABLES,
    RuntimePrivilegeError,
    _changed_privileges,
    _load_url,
    assess,
)


def _env(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "database.env"
    path.write_text(f"DATABASE_URL={value}\n", encoding="utf-8")
    return path


def _role(**changes):
    value = {
        "rolname": "beta10d_forecast_login",
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "rolcanlogin": True,
        "group_member": True,
        "schema_usage": True,
        "schema_create": False,
    }
    value.update(changes)
    return value


def _privileges(*, append_ready: bool = True):
    rows = {
        table: {"select": True, "insert": False, "update": False, "delete": False}
        for table in READ_ONLY_TABLES
    }
    rows.update(
        {
            table: {
                "select": append_ready,
                "insert": append_ready,
                "update": False,
                "delete": False,
            }
            for table in APPEND_TABLES
        }
    )
    return rows


def test_urls_are_fixed_to_local_postgres_and_expected_roles(tmp_path: Path) -> None:
    admin = _load_url(
        _env(tmp_path, "postgresql+psycopg://postgres:secret@localhost:5432/postgres"),
        expected_user="postgres",
    )
    assert admin.username == "postgres"
    runtime = _load_url(
        _env(
            tmp_path,
            "postgresql+psycopg://beta10d_forecast_login:secret@localhost:5432/postgres",
        ),
        expected_user="beta10d_forecast_login",
    )
    assert runtime.username == "beta10d_forecast_login"


@pytest.mark.parametrize(
    ("value", "user"),
    [
        ("postgresql+psycopg://postgres:secret@remote:5432/postgres", "postgres"),
        ("postgresql+psycopg://postgres:secret@localhost:5433/postgres", "postgres"),
        ("postgresql+psycopg://postgres:secret@localhost:5432/other", "postgres"),
        ("postgresql+psycopg://other:secret@localhost:5432/postgres", "postgres"),
    ],
)
def test_url_scope_expansion_is_rejected(tmp_path: Path, value: str, user: str) -> None:
    with pytest.raises(RuntimePrivilegeError, match="^database_target_rejected"):
        _load_url(_env(tmp_path, value), expected_user=user)


def test_exact_runtime_privileges_pass() -> None:
    assert assess(_role(), _privileges()) == {"status": "PASS", "issues": []}


def test_missing_append_privileges_are_explicit() -> None:
    result = assess(_role(), _privileges(append_ready=False))
    assert result["status"] == "NOT_PASS"
    assert len(result["issues"]) == 6
    assert all(issue.startswith("append_privilege_missing:") for issue in result["issues"])


@pytest.mark.parametrize(
    ("role_changes", "table", "privilege", "reason"),
    [
        ({"rolsuper": True}, None, None, "dangerous_role_attribute:rolsuper"),
        ({"schema_create": True}, None, None, "dangerous_role_attribute:schema_create"),
        ({}, "kb_chunks", "insert", "readonly_privilege_forbidden:kb_chunks:insert"),
        (
            {},
            "kb_rag_audit_events",
            "delete",
            "append_privilege_forbidden:kb_rag_audit_events:delete",
        ),
    ],
)
def test_dangerous_privilege_drift_fails_closed(
    role_changes, table, privilege, reason
) -> None:
    rows = _privileges()
    if table and privilege:
        rows[table][privilege] = True
    result = assess(_role(**role_changes), rows)
    assert result["status"] == "NOT_PASS"
    assert reason in result["issues"]


def test_change_counter_is_exact_and_idempotent() -> None:
    before = {"table_privileges": _privileges(append_ready=False)}
    after = {"table_privileges": _privileges()}
    assert _changed_privileges(before, after) == 6
    assert _changed_privileges(after, after) == 0
