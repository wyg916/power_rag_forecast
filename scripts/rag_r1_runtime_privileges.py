from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError


ADMIN_USER = "postgres"
RUNTIME_LOGIN = "beta10d_forecast_login"
RUNTIME_GROUP = "beta10d_forecast_runtime"
READ_ONLY_TABLES = (
    "kb_documents",
    "kb_document_versions",
    "kb_chunks",
    "kb_releases",
    "kb_release_items",
)
APPEND_TABLES = (
    "kb_retrieval_runs",
    "kb_citations",
    "kb_rag_audit_events",
)
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")


class RuntimePrivilegeError(RuntimeError):
    pass


def _load_url(path: Path, *, expected_user: str) -> URL:
    values = dotenv_values(path)
    raw = str(values.get("MIGRATION_DATABASE_URL") or values.get("DATABASE_URL") or "")
    if not raw:
        raise RuntimePrivilegeError("database_url_missing")
    url = make_url(raw)
    actual = {
        "host": (url.host or "").lower(),
        "port": url.port or 5432,
        "database": url.database or "",
        "user": url.username or "",
    }
    expected = {
        "host": "localhost",
        "port": 5432,
        "database": "postgres",
        "user": expected_user,
    }
    if actual != expected:
        raise RuntimePrivilegeError(f"database_target_rejected:{actual}")
    return url


def _role_state(connection: Any) -> dict[str, Any]:
    row = connection.execute(
        text(
            """
            SELECT current_user, session_user, rolname, rolsuper, rolcreatedb,
                   rolcreaterole, rolreplication, rolbypassrls, rolcanlogin,
                   pg_has_role(:runtime_login, :runtime_group, 'MEMBER') AS group_member,
                   has_schema_privilege(:runtime_login, 'public', 'USAGE') AS schema_usage,
                   has_schema_privilege(:runtime_login, 'public', 'CREATE') AS schema_create
            FROM pg_roles
            WHERE rolname = :runtime_login
            """
        ),
        {"runtime_login": RUNTIME_LOGIN, "runtime_group": RUNTIME_GROUP},
    ).mappings().one()
    return dict(row)


def _table_privileges(connection: Any) -> dict[str, dict[str, bool]]:
    result: dict[str, dict[str, bool]] = {}
    for table in (*READ_ONLY_TABLES, *APPEND_TABLES):
        result[table] = {
            privilege.lower(): bool(
                connection.execute(
                    text("SELECT has_table_privilege(:role, :table, :privilege)"),
                    {
                        "role": RUNTIME_LOGIN,
                        "table": f"public.{table}",
                        "privilege": privilege,
                    },
                ).scalar_one()
            )
            for privilege in PRIVILEGES
        }
    return result


def assess(
    role: Mapping[str, Any], privileges: Mapping[str, Mapping[str, bool]]
) -> dict[str, Any]:
    issues: list[str] = []
    if role.get("rolname") != RUNTIME_LOGIN or not role.get("rolcanlogin"):
        issues.append("runtime_identity_invalid")
    for attribute in (
        "rolsuper",
        "rolcreatedb",
        "rolcreaterole",
        "rolreplication",
        "rolbypassrls",
        "schema_create",
    ):
        if role.get(attribute):
            issues.append(f"dangerous_role_attribute:{attribute}")
    if not role.get("group_member"):
        issues.append("runtime_group_membership_missing")
    if not role.get("schema_usage"):
        issues.append("public_schema_usage_missing")
    for table in READ_ONLY_TABLES:
        state = privileges.get(table, {})
        if not state.get("select"):
            issues.append(f"required_select_missing:{table}")
        for privilege in ("insert", "update", "delete"):
            if state.get(privilege):
                issues.append(f"readonly_privilege_forbidden:{table}:{privilege}")
    for table in APPEND_TABLES:
        state = privileges.get(table, {})
        for privilege in ("select", "insert"):
            if not state.get(privilege):
                issues.append(f"append_privilege_missing:{table}:{privilege}")
        for privilege in ("update", "delete"):
            if state.get(privilege):
                issues.append(f"append_privilege_forbidden:{table}:{privilege}")
    return {"status": "PASS" if not issues else "NOT_PASS", "issues": issues}


def _safe_state(role: Mapping[str, Any], privileges: Mapping[str, Mapping[str, bool]]) -> dict[str, Any]:
    return {
        "role": {
            key: role.get(key)
            for key in (
                "rolname",
                "rolsuper",
                "rolcreatedb",
                "rolcreaterole",
                "rolreplication",
                "rolbypassrls",
                "rolcanlogin",
                "group_member",
                "schema_usage",
                "schema_create",
            )
        },
        "table_privileges": {table: dict(values) for table, values in privileges.items()},
        "assessment": assess(role, privileges),
    }


def inspect_runtime(runtime_url: URL) -> dict[str, Any]:
    engine = create_engine(
        runtime_url,
        pool_pre_ping=True,
        future=True,
        connect_args={
            "hostaddr": "127.0.0.1",
            "options": "-c default_transaction_read_only=on",
            "connect_timeout": 5,
        },
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            role = _role_state(connection)
            if role["current_user"] != RUNTIME_LOGIN or role["session_user"] != RUNTIME_LOGIN:
                raise RuntimePrivilegeError("runtime_session_identity_invalid")
            privileges = _table_privileges(connection)
            connection.rollback()
    finally:
        engine.dispose()
    return _safe_state(role, privileges)


def _assert_no_dangerous_drift(state: Mapping[str, Any]) -> None:
    issues = state["assessment"]["issues"]
    allowed_prefixes = ("append_privilege_missing:",)
    dangerous = [issue for issue in issues if not issue.startswith(allowed_prefixes)]
    if dangerous:
        raise RuntimePrivilegeError(f"runtime_privilege_drift:{dangerous}")


def _grant(connection: Any) -> None:
    for table in APPEND_TABLES:
        connection.execute(
            text(f"GRANT SELECT, INSERT ON TABLE public.{table} TO {RUNTIME_GROUP}")
        )


def _revoke(connection: Any) -> None:
    for table in APPEND_TABLES:
        connection.execute(
            text(f"REVOKE SELECT, INSERT ON TABLE public.{table} FROM {RUNTIME_GROUP}")
        )


def _admin_state(connection: Any) -> dict[str, Any]:
    return _safe_state(_role_state(connection), _table_privileges(connection))


def _changed_privileges(before: Mapping[str, Any], after: Mapping[str, Any]) -> int:
    count = 0
    for table in (*READ_ONLY_TABLES, *APPEND_TABLES):
        for privilege in PRIVILEGES:
            key = privilege.lower()
            if before["table_privileges"][table][key] != after["table_privileges"][table][key]:
                count += 1
    return count


def _expect_denied(runtime_url: URL, statement: str) -> str:
    engine = create_engine(
        runtime_url,
        pool_pre_ping=True,
        future=True,
        connect_args={"hostaddr": "127.0.0.1", "connect_timeout": 5},
    )
    try:
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
        except DBAPIError as exc:
            sqlstate = str(getattr(exc.orig, "sqlstate", "") or "")
            if sqlstate != "42501":
                raise RuntimePrivilegeError(
                    f"runtime_denial_sqlstate_invalid:{sqlstate or 'missing'}"
                ) from exc
            return sqlstate
    finally:
        engine.dispose()
    raise RuntimePrivilegeError("runtime_forbidden_operation_allowed")


def _write_probe(runtime_url: URL) -> dict[str, Any]:
    probe_id = "rag_r1_runtime_privilege_probe"
    engine = create_engine(
        runtime_url,
        pool_pre_ping=True,
        future=True,
        connect_args={"hostaddr": "127.0.0.1", "connect_timeout": 5},
    )
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            chunk = connection.execute(
                text(
                    """
                    SELECT version_id, chunk_id, content_sha256
                    FROM kb_chunks
                    WHERE tenant_id='default' AND version_id IS NOT NULL
                    ORDER BY chunk_id
                    LIMIT 1
                    """
                )
            ).mappings().one()
            connection.execute(
                text(
                    """
                    INSERT INTO kb_retrieval_runs
                      (tenant_id,retrieval_run_id,release_id,actor_id,acl_fingerprint,
                       query_sha256,filters_json,requested_top_k,returned_count,status,
                       degraded_components_json,timings_json,run_id,trace_id)
                    VALUES
                      ('default',:id,'RAG-R1','runtime-probe',:hash,:hash,'{}'::jsonb,
                       1,1,'available','[]'::jsonb,'{}'::jsonb,:id,:id)
                    """
                ),
                {"id": probe_id, "hash": "0" * 64},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO kb_citations
                      (tenant_id,citation_id,retrieval_run_id,release_id,claim_id,
                       version_id,chunk_id,locator_json,content_sha256,verified)
                    VALUES
                      ('default',:id,:id,'RAG-R1',:id,:version_id,:chunk_id,
                       '{}'::jsonb,:content_sha256,true)
                    """
                ),
                {"id": probe_id, **dict(chunk)},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO kb_rag_audit_events
                      (tenant_id,event_id,event_type,actor_id,resource_type,resource_id,
                       release_id,run_id,trace_id,status,details_json)
                    VALUES
                      ('default',:id,'runtime_privilege_probe','runtime-probe',
                       'retrieval_run',:id,'RAG-R1',:id,:id,'success','{}'::jsonb)
                    """
                ),
                {"id": probe_id},
            )
            visible = {
                table: int(
                    connection.execute(
                        text(
                            f"SELECT COUNT(*) FROM {table} WHERE tenant_id='default' "
                            f"AND {identifier}=:id"
                        ),
                        {"id": probe_id},
                    ).scalar_one()
                )
                for table, identifier in (
                    ("kb_retrieval_runs", "retrieval_run_id"),
                    ("kb_citations", "citation_id"),
                    ("kb_rag_audit_events", "event_id"),
                )
            }
            if visible != {table: 1 for table in visible}:
                raise RuntimePrivilegeError(f"runtime_write_probe_incomplete:{visible}")
            transaction.rollback()
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            restored = {
                table: int(
                    connection.execute(
                        text(
                            f"SELECT COUNT(*) FROM {table} WHERE tenant_id='default' "
                            f"AND {identifier}=:id"
                        ),
                        {"id": probe_id},
                    ).scalar_one()
                )
                for table, identifier in (
                    ("kb_retrieval_runs", "retrieval_run_id"),
                    ("kb_citations", "citation_id"),
                    ("kb_rag_audit_events", "event_id"),
                )
            }
            connection.rollback()
    finally:
        engine.dispose()
    if any(restored.values()):
        raise RuntimePrivilegeError(f"runtime_write_probe_not_restored:{restored}")
    denied = {
        "retrieval_update": _expect_denied(
            runtime_url, "UPDATE kb_retrieval_runs SET status='error' WHERE false"
        ),
        "citation_delete": _expect_denied(
            runtime_url, "DELETE FROM kb_citations WHERE false"
        ),
        "release_insert": _expect_denied(
            runtime_url,
            "INSERT INTO kb_releases (tenant_id,release_id) VALUES ('default','forbidden')",
        ),
    }
    return {
        "status": "PASS",
        "transaction_rolled_back": True,
        "append_rows_visible_before_rollback": visible,
        "append_rows_after_rollback": restored,
        "denied_sqlstates": denied,
        "database_business_writes": 0,
    }


def run(admin_url: URL, runtime_url: URL, mode: str) -> dict[str, Any]:
    before = inspect_runtime(runtime_url)
    if mode == "verify":
        return {"mode": mode, "before": before, "database_privilege_changes": 0}
    if mode == "write-probe":
        if before["assessment"]["status"] != "PASS":
            raise RuntimePrivilegeError("runtime_write_probe_privileges_not_ready")
        return {
            "mode": mode,
            "before": before,
            "probe": _write_probe(runtime_url),
            "database_privilege_changes": 0,
        }
    _assert_no_dangerous_drift(before)
    admin_engine = create_engine(
        admin_url,
        pool_pre_ping=True,
        future=True,
        connect_args={"hostaddr": "127.0.0.1", "connect_timeout": 5},
    )
    try:
        if mode == "rollback-probe":
            with admin_engine.connect() as connection:
                transaction = connection.begin()
                _grant(connection)
                probe = _admin_state(connection)
                if probe["assessment"]["status"] != "PASS":
                    raise RuntimePrivilegeError("rollback_probe_grant_gate_failed")
                transaction.rollback()
            restored = inspect_runtime(runtime_url)
            if restored != before:
                raise RuntimePrivilegeError("rollback_probe_not_restored")
            return {
                "mode": mode,
                "status": "PASS",
                "transaction_rolled_back": True,
                "probe": probe,
                "restored": restored,
                "database_privilege_changes": 0,
            }
        with admin_engine.begin() as connection:
            if mode == "apply":
                _grant(connection)
            elif mode == "revoke":
                _revoke(connection)
            else:
                raise RuntimePrivilegeError("mode_invalid")
    finally:
        admin_engine.dispose()
    after = inspect_runtime(runtime_url)
    if mode == "apply" and after["assessment"]["status"] != "PASS":
        raise RuntimePrivilegeError("runtime_privilege_apply_gate_failed")
    if mode == "revoke":
        _assert_no_dangerous_drift(after)
    return {
        "mode": mode,
        "status": "PASS",
        "before": before,
        "after": after,
        "database_privilege_changes": _changed_privileges(before, after),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage fixed RAG-R1 runtime privileges.")
    parser.add_argument("--admin-config", type=Path, required=True)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("verify", "rollback-probe", "apply", "write-probe", "revoke"),
        required=True,
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise RuntimePrivilegeError(f"report_already_exists:{args.report}")
    admin_url = _load_url(args.admin_config, expected_user=ADMIN_USER)
    runtime_url = _load_url(args.runtime_config, expected_user=RUNTIME_LOGIN)
    result = run(admin_url, runtime_url, args.mode)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "status": result.get("status") or result.get("before", {}).get("assessment", {}).get("status"),
                "database_privilege_changes": result["database_privilege_changes"],
                "report": str(args.report),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
