from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
from typing import Iterable

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_GROUP = "beta10d_app_runtime"
RUNTIME_LOGIN = "beta10d_app_login"
SECURITY_GROUP = "beta10d_security_runtime"
SECURITY_LOGIN = "beta10d_security_login"

MIGRATION_TABLES = frozenset({"alembic_version", "schema_migrations"})
SECURITY_TABLES = frozenset(
    {
        "audit_logs",
        "roles",
        "system_api_configs",
        "system_api_test_logs",
        "system_runtime_config",
        "user_roles",
        "users",
    }
)
BUSINESS_TABLES = (
    "ai_answer_feedback",
    "ai_chat_feedback",
    "ai_chat_messages",
    "ai_chat_sessions",
    "ai_conversation_state",
    "ai_prompt_templates",
    "ai_qa_test_cases",
    "ai_report_review_runs",
    "ai_tool_call_logs",
    "ai_traces",
    "ai_memory_admissions",
    "ai_memory_deletion_jobs",
    "ai_memory_deletion_proofs",
    "ai_memory_legal_holds",
    "ai_memory_outbox",
    "ai_memory_records",
    "ai_memory_relations",
    "ai_memory_state_transitions",
    "ai_memory_usage",
    "ai_memory_versions",
    "analysis_runs",
    "anomaly_explanations",
    "chatbi_analysis_plans",
    "feature_importance",
    "forecast_input_batches",
    "forecast_input_snapshots",
    "forecast_results",
    "forecast_runs",
    "kb_chunks",
    "kb_documents",
    "kb_qa_tests",
    "kb_search_results",
    "market_power_price_rules",
    "model_comparison_runs",
    "model_error_memory",
    "model_evaluation_runs",
    "model_governance_events",
    "model_metrics",
    "model_performance_daily",
    "model_prediction_comparison_points",
    "model_registry",
    "model_retrain_jobs",
    "model_strategy_memory",
    "model_versions",
    "monitoring_metrics",
    "prediction_tracking",
    "pv_policy_files",
    "pv_station_tariff_check",
    "pv_tariff_period_rules",
    "pv_tariff_rules",
    "raw_load",
    "raw_market",
    "raw_renewable",
    "raw_weather",
    "report_approval_runs",
    "report_reviews",
    "report_runs",
    "southern_grid_tax_rules",
    "storage_devices",
    "storage_soc_snapshots",
    "strategy_advice",
    "strategy_execution_items",
    "strategy_reviews",
    "system_health_snapshots",
    "task_logs",
    "task_runs",
)
BUSINESS_READ_ONLY_TABLES = (
    "chatbi_dimension_catalog",
    "chatbi_join_catalog",
    "chatbi_metric_catalog",
    "kb_document_versions",
    "kb_rag_audit_events",
    "kb_release_items",
    "kb_releases",
)
BUSINESS_VIEWS = (
    "model_feature_importance",
    "raw_actual_load",
    "raw_da_price",
    "raw_forecast_load_selected",
    "raw_rt_price",
    "vw_latest_active_model",
    "vw_model_comparison",
    "vw_recent_model_errors",
)
BUSINESS_INSERT_ONLY_TABLES = frozenset(
    {
        "forecast_input_batches",
        "forecast_input_snapshots",
    }
)
BUSINESS_WRITE_TABLES = frozenset(BUSINESS_TABLES) - BUSINESS_INSERT_ONLY_TABLES
RUNTIME_SEQUENCE_TABLES = BUSINESS_WRITE_TABLES | BUSINESS_INSERT_ONLY_TABLES | frozenset({"audit_logs"})
DELETE_TABLES = frozenset(
    {
        "ai_answer_feedback",
        "ai_chat_feedback",
        "ai_chat_messages",
        "ai_chat_sessions",
        "ai_conversation_state",
        "ai_tool_call_logs",
        "ai_traces",
        "raw_load",
        "raw_market",
        "raw_renewable",
        "raw_weather",
    }
)


def _migration_url() -> URL:
    value = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("缺少 MIGRATION_DATABASE_URL。")
    parsed = make_url(value)
    if not parsed.drivername.startswith("postgresql"):
        raise RuntimeError("MIGRATION_DATABASE_URL 必须指向 PostgreSQL。")
    return parsed


def _connect(url: URL) -> psycopg.Connection:
    return psycopg.connect(
        host=url.host or "localhost",
        port=url.port or 5432,
        dbname=url.database or "postgres",
        user=url.username or "",
        password=url.password or "",
        connect_timeout=5,
    )


def _assert_external_config(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return resolved
    raise RuntimeError("本地凭据文件必须位于项目目录外。")


def _url_for(base: URL, username: str, password: str) -> str:
    return URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=base.host or "localhost",
        port=base.port or 5432,
        database=base.database or "postgres",
    ).render_as_string(hide_password=False)


def _load_or_create_passwords(path: Path, base: URL) -> tuple[str, str]:
    if path.exists():
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if "=" not in raw_line or raw_line.lstrip().startswith("#"):
                continue
            key, value = raw_line.split("=", 1)
            values[key.strip()] = value.strip()
        runtime = make_url(values.get("DATABASE_URL", ""))
        security = make_url(values.get("SECURITY_DATABASE_URL", ""))
        if runtime.username != RUNTIME_LOGIN or security.username != SECURITY_LOGIN or not runtime.password or not security.password:
            raise RuntimeError("现有本地配置不符合 Day 4 角色映射，拒绝覆盖。")
        return str(runtime.password), str(security.password)
    path.parent.mkdir(parents=True, exist_ok=True)
    runtime_password = os.environ.get("APP_DB_PASSWORD", "").strip()
    security_password = os.environ.get("SECURITY_DB_PASSWORD", "").strip()
    if bool(runtime_password) != bool(security_password):
        raise RuntimeError("APP_DB_PASSWORD 与 SECURITY_DB_PASSWORD 必须同时提供或同时留空。")
    runtime_password = runtime_password or secrets.token_urlsafe(36)
    security_password = security_password or secrets.token_urlsafe(36)
    if len(runtime_password) < 24 or len(security_password) < 24:
        raise RuntimeError("数据库运行身份密码长度必须至少为 24 个字符。")
    content = (
        "# Day 4 local database identities. Never commit this file.\n"
        f"DATABASE_URL={_url_for(base, RUNTIME_LOGIN, runtime_password)}\n"
        f"SECURITY_DATABASE_URL={_url_for(base, SECURITY_LOGIN, security_password)}\n"
    )
    path.write_text(content, encoding="utf-8")
    return runtime_password, security_password


def _qualified(name: str) -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier("public"), sql.Identifier(name))


def _role(cur: psycopg.Cursor, group: str, login: str, password: str) -> None:
    for role in (group, login):
        exists = cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        if not exists:
            cur.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
    cur.execute(
        sql.SQL("ALTER ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(
            sql.Identifier(group)
        )
    )
    cur.execute(
        sql.SQL(
            "ALTER ROLE {} LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
        ).format(sql.Identifier(login), sql.Literal(password))
    )
    cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(login)))
    cur.execute(sql.SQL("ALTER ROLE {} SET search_path = public, pg_catalog").format(sql.Identifier(login)))


def _revoke_objects(cur: psycopg.Cursor, objects: Iterable[str], roles: tuple[str, ...]) -> None:
    role_list = sql.SQL(", ").join(sql.Identifier(role) for role in roles)
    for name in objects:
        cur.execute(sql.SQL("REVOKE ALL PRIVILEGES ON TABLE {} FROM {}").format(_qualified(name), role_list))


def _grant(cur: psycopg.Cursor, privileges: str, objects: Iterable[str], role: str, *, object_kind: str = "TABLE") -> None:
    for name in objects:
        cur.execute(
            sql.SQL("GRANT " + privileges + " ON " + object_kind + " {} TO {}").format(
                _qualified(name), sql.Identifier(role)
            )
        )


def _sequence_grantees(owner_table: str) -> tuple[str, ...]:
    roles: list[str] = []
    if owner_table in RUNTIME_SEQUENCE_TABLES:
        roles.append(RUNTIME_GROUP)
    if owner_table in SECURITY_TABLES:
        roles.append(SECURITY_GROUP)
    return tuple(roles)


def apply_security(local_config: Path) -> dict[str, object]:
    base = _migration_url()
    config_path = _assert_external_config(local_config)
    runtime_password, security_password = _load_or_create_passwords(config_path, base)
    with _connect(base) as conn:
        with conn.cursor() as cur:
            current = cur.execute(
                "SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            if not current or not current[1]:
                raise RuntimeError("Day 4 ACL 落地必须由当前维护身份执行。")
            database = base.database or "postgres"
            _role(cur, RUNTIME_GROUP, RUNTIME_LOGIN, runtime_password)
            _role(cur, SECURITY_GROUP, SECURITY_LOGIN, security_password)
            all_objects = (
                *BUSINESS_TABLES,
                *BUSINESS_READ_ONLY_TABLES,
                *BUSINESS_VIEWS,
                *SECURITY_TABLES,
                *MIGRATION_TABLES,
            )
            project_roles = (RUNTIME_GROUP, RUNTIME_LOGIN, SECURITY_GROUP, SECURITY_LOGIN)
            _revoke_objects(cur, all_objects, project_roles)
            for role in project_roles:
                cur.execute(sql.SQL("REVOKE CREATE ON DATABASE {} FROM {}").format(sql.Identifier(database), sql.Identifier(role)))
                cur.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(sql.Identifier(role)))
                cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(role)))
                cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            _grant(
                cur,
                "SELECT",
                (*BUSINESS_TABLES, *BUSINESS_READ_ONLY_TABLES, *BUSINESS_VIEWS),
                RUNTIME_GROUP,
            )
            _grant(cur, "INSERT, UPDATE", BUSINESS_WRITE_TABLES, RUNTIME_GROUP)
            _grant(cur, "INSERT", BUSINESS_INSERT_ONLY_TABLES, RUNTIME_GROUP)
            _grant(cur, "DELETE", DELETE_TABLES, RUNTIME_GROUP)
            _grant(cur, "INSERT", ("audit_logs",), RUNTIME_GROUP)
            _grant(cur, "SELECT, INSERT, UPDATE", SECURITY_TABLES, SECURITY_GROUP)
            sequences = [
                row[0]
                for row in cur.execute(
                    "SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename"
                ).fetchall()
            ]
            for sequence in sequences:
                owner_table = sequence.removesuffix("_id_seq")
                for role in _sequence_grantees(owner_table):
                    _grant(cur, "USAGE, SELECT", (sequence,), role, object_kind="SEQUENCE")
        conn.commit()
    return {
        "runtime_group": RUNTIME_GROUP,
        "runtime_login": RUNTIME_LOGIN,
        "security_group": SECURITY_GROUP,
        "security_login": SECURITY_LOGIN,
        "business_select_objects": len(BUSINESS_TABLES)
        + len(BUSINESS_READ_ONLY_TABLES)
        + len(BUSINESS_VIEWS),
        "security_objects": len(SECURITY_TABLES),
        "local_config": str(config_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Day 4 project-scoped PostgreSQL roles and ACLs.")
    parser.add_argument("--apply", action="store_true", help="Apply the idempotent role and ACL manifest.")
    parser.add_argument("--local-config", type=Path, required=True)
    args = parser.parse_args()
    if not args.apply:
        raise RuntimeError("必须显式传入 --apply。")
    result = apply_security(args.local_config)
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
