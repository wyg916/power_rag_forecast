from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, inspect, make_url, text
from sqlalchemy.engine import Engine, URL

from config_loader import load_dotenv


TEST_SCHEMA_PREFIX = "beta10d_day3_close_"
TEST_ROLE_SUFFIX = "_role"
EXPECTED_DATABASE = "postgres"
EXPECTED_USER = "postgres"
EXPECTED_HOSTS = {"localhost", "127.0.0.1", "::1"}
EXPECTED_PORT = 5432
EXPECTED_ALEMBIC_HEAD = "0022_chatbi_semantic_v1"
EXPECTED_ALEMBIC_HEAD_ENV = "BETA10D_TEST_EXPECTED_ALEMBIC_HEAD"
ISOLATION_FLAG = "BETA10D_TEST_ISOLATION_ACTIVE"
SCHEMA_ENV = "BETA10D_TEST_SCHEMA"
ROLE_ENV = "BETA10D_TEST_ROLE"
MODE_ENV = "BETA10D_TEST_DATABASE_MODE"
SECURITY_DATABASE_URL_ENV = "SECURITY_DATABASE_URL"
MIGRATION_DATABASE_URL_ENV = "MIGRATION_DATABASE_URL"
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_SECRET_URL_RE = re.compile(r"(postgres(?:ql)?(?:\+\w+)?://[^:\s/@]+:)[^@\s]+(@)", re.IGNORECASE)


class DatabaseIsolationError(RuntimeError):
    """Raised before tests can use an unsafe PostgreSQL target."""


def _safe_error(value: object) -> str:
    return _SECRET_URL_RE.sub(r"\1***\2", str(value))


def validate_isolated_identifier(value: str, *, kind: str) -> str:
    candidate = str(value or "").strip()
    if not _IDENTIFIER_RE.fullmatch(candidate):
        raise DatabaseIsolationError(f"{kind} 不是安全的 PostgreSQL 标识符")
    if not candidate.startswith(TEST_SCHEMA_PREFIX):
        raise DatabaseIsolationError(f"{kind} 未通过 {TEST_SCHEMA_PREFIX} 前缀门禁")
    if candidate == "public":
        raise DatabaseIsolationError(f"{kind} 不得为 public")
    return candidate


def validate_database_target(database_url: str) -> URL:
    value = str(database_url or "").strip()
    if not value:
        raise DatabaseIsolationError("隔离测试缺少 DATABASE_URL")
    parsed = make_url(value)
    if not parsed.drivername.startswith("postgresql"):
        raise DatabaseIsolationError("隔离测试数据库方言必须为 PostgreSQL")
    actual = {
        "database": parsed.database or "",
        "user": parsed.username or "",
        "host": parsed.host or "",
        "port": parsed.port or EXPECTED_PORT,
    }
    if actual["database"] != EXPECTED_DATABASE:
        raise DatabaseIsolationError("隔离测试数据库名必须为 postgres")
    if actual["user"] != EXPECTED_USER:
        raise DatabaseIsolationError("隔离测试连接用户必须为 postgres")
    if actual["host"] not in EXPECTED_HOSTS:
        raise DatabaseIsolationError("隔离测试数据库主机必须为本机")
    if actual["port"] != EXPECTED_PORT:
        raise DatabaseIsolationError("隔离测试数据库端口必须为 5432")
    return parsed


def build_isolated_runtime_url(database_url: str, schema: str, role: str) -> str:
    parsed = validate_database_target(database_url)
    schema = validate_isolated_identifier(schema, kind="测试 Schema")
    role = validate_isolated_identifier(role, kind="测试角色")
    if role != f"{schema}{TEST_ROLE_SUFFIX}":
        raise DatabaseIsolationError("测试角色必须与测试 Schema 精确绑定")
    options = f"-csearch_path={schema},pg_catalog -crole={role}"
    return parsed.update_query_dict({"options": options}).render_as_string(hide_password=False)


def build_isolated_security_url(runtime_url: str) -> str:
    """Keep security repositories on the same disposable test identity."""

    parsed = make_url(runtime_url)
    query = dict(parsed.query)
    query["application_name"] = "beta10d_security_isolated"
    return parsed.set(query=query).render_as_string(hide_password=False)


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise DatabaseIsolationError("拒绝引用不安全的 PostgreSQL 标识符")
    return f'"{value}"'


def _target_summary(parsed: URL) -> dict[str, Any]:
    return {
        "driver": parsed.drivername,
        "database": parsed.database,
        "user": parsed.username,
        "host": parsed.host,
        "port": parsed.port or EXPECTED_PORT,
    }


def verify_isolated_runtime(database_url: str, schema: str, role: str) -> dict[str, Any]:
    parsed = validate_database_target(database_url)
    schema = validate_isolated_identifier(schema, kind="测试 Schema")
    role = validate_isolated_identifier(role, kind="测试角色")
    if role != f"{schema}{TEST_ROLE_SUFFIX}":
        raise DatabaseIsolationError("测试角色必须与测试 Schema 精确绑定")

    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    try:
        with engine.connect() as connection:
            identity = dict(
                connection.execute(
                    text(
                        """
                        SELECT current_database() AS database_name,
                               current_user AS current_user,
                               session_user AS session_user,
                               current_schema() AS current_schema,
                               current_schemas(false) AS current_schemas,
                               current_setting('search_path') AS search_path,
                               inet_server_addr()::text AS server_addr,
                               inet_server_port() AS server_port
                        """
                    )
                ).mappings().one()
            )
            if identity["database_name"] != EXPECTED_DATABASE:
                raise DatabaseIsolationError("运行时数据库身份不是 postgres")
            if identity["session_user"] != EXPECTED_USER:
                raise DatabaseIsolationError("运行时 session_user 不是 postgres")
            if identity["current_user"] != role:
                raise DatabaseIsolationError("运行时未切换到受限测试角色")
            if identity["current_schema"] != schema:
                raise DatabaseIsolationError("运行时 current_schema 不是隔离 Schema")
            current_schemas = list(identity["current_schemas"] or [])
            if not current_schemas or current_schemas[0] != schema or "public" in current_schemas:
                raise DatabaseIsolationError("运行时 search_path 未与 public 完全隔离")

            owner = connection.execute(
                text(
                    """
                    SELECT pg_get_userbyid(nspowner)
                    FROM pg_namespace
                    WHERE nspname = :schema
                    """
                ),
                {"schema": schema},
            ).scalar_one_or_none()
            if owner != role:
                raise DatabaseIsolationError("隔离 Schema owner 与受限测试角色不一致")

            version_table = connection.execute(
                text("SELECT to_regclass(:qualified)"),
                {"qualified": f"{schema}.alembic_version"},
            ).scalar_one()
            if version_table is None:
                raise DatabaseIsolationError("Alembic version table 不在隔离 Schema")
            head = connection.execute(
                text(f"SELECT version_num FROM {_quote_identifier(schema)}.alembic_version")
            ).scalar_one()
            expected_head = os.environ.get(EXPECTED_ALEMBIC_HEAD_ENV, EXPECTED_ALEMBIC_HEAD).strip()
            if head != expected_head:
                raise DatabaseIsolationError("隔离 Schema Alembic head 不正确")

            role_flags = dict(
                connection.execute(
                    text(
                        """
                        SELECT rolsuper, rolinherit, rolcreaterole, rolcreatedb,
                               rolcanlogin, rolreplication, rolbypassrls
                        FROM pg_roles
                        WHERE rolname = :role
                        """
                    ),
                    {"role": role},
                ).mappings().one()
            )
            dangerous_flags = (
                role_flags["rolsuper"]
                or role_flags["rolinherit"]
                or role_flags["rolcreaterole"]
                or role_flags["rolcreatedb"]
                or role_flags["rolcanlogin"]
                or role_flags["rolreplication"]
                or role_flags["rolbypassrls"]
            )
            if dangerous_flags:
                raise DatabaseIsolationError("临时测试角色权限超出最小边界")

            public_privileges = dict(
                connection.execute(
                    text(
                        """
                        SELECT has_schema_privilege(current_user, 'public', 'CREATE') AS schema_create,
                               has_table_privilege(
                                   current_user,
                                   'public.audit_logs',
                                   'INSERT,UPDATE,DELETE'
                               ) AS audit_write,
                               has_sequence_privilege(
                                   current_user,
                                   'public.audit_logs_id_seq',
                                   'USAGE,UPDATE'
                               ) AS audit_sequence_write
                        """
                    )
                ).mappings().one()
            )
            if any(public_privileges.values()):
                raise DatabaseIsolationError("临时测试角色仍可写入 public")
    finally:
        engine.dispose()

    return {
        "target": _target_summary(parsed),
        "identity": identity,
        "schema_owner": owner,
        "alembic_head": head,
        "role_flags": role_flags,
        "public_write_privileges": public_privileges,
    }


def configure_pytest_database() -> dict[str, Any]:
    """Run before importing the application in tests/conftest.py.

    Normal pytest runs cannot inherit the repository's local DATABASE_URL.
    Database integration tests must be launched by this module's isolated
    runner, which injects a restricted role and isolated search_path.
    """

    load_dotenv()
    if os.environ.get(ISOLATION_FLAG, "").strip() != "1":
        had_database_url = bool(os.environ.get("DATABASE_URL", "").strip())
        had_security_database_url = bool(os.environ.get(SECURITY_DATABASE_URL_ENV, "").strip())
        had_migration_database_url = bool(os.environ.get(MIGRATION_DATABASE_URL_ENV, "").strip())
        os.environ["DATABASE_URL"] = ""
        os.environ[SECURITY_DATABASE_URL_ENV] = ""
        os.environ[MIGRATION_DATABASE_URL_ENV] = ""
        os.environ[MODE_ENV] = "disabled-no-database"
        readonly_option = "-c default_transaction_read_only=on"
        current_options = os.environ.get("PGOPTIONS", "").strip()
        if "default_transaction_read_only" not in current_options:
            os.environ["PGOPTIONS"] = f"{current_options} {readonly_option}".strip()
        return {
            "mode": "disabled-no-database",
            "local_database_url_was_blocked": had_database_url,
            "security_database_url_was_blocked": had_security_database_url,
            "migration_database_url_was_blocked": had_migration_database_url,
            "server_default_transaction_read_only": True,
        }

    schema = validate_isolated_identifier(os.environ.get(SCHEMA_ENV, ""), kind="测试 Schema")
    role = validate_isolated_identifier(os.environ.get(ROLE_ENV, ""), kind="测试角色")
    runtime = verify_isolated_runtime(os.environ.get("DATABASE_URL", ""), schema, role)
    security_runtime = verify_isolated_runtime(
        os.environ.get(SECURITY_DATABASE_URL_ENV, ""), schema, role
    )
    os.environ[MODE_ENV] = "isolated-schema"
    return {"mode": "isolated-schema", **runtime, "security_runtime": security_runtime}


def _public_snapshot(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        inspector = inspect(connection)
        quote = connection.dialect.identifier_preparer.quote
        tables = sorted(inspector.get_table_names(schema="public"))
        fingerprints: dict[str, dict[str, Any]] = {}
        for table in tables:
            row = connection.execute(
                text(
                    f"""
                    SELECT count(*)::bigint AS row_count,
                           md5(COALESCE(string_agg(
                               to_jsonb(t)::text,
                               E'\\n' ORDER BY to_jsonb(t)::text
                           ), '')) AS content_md5
                    FROM public.{quote(table)} AS t
                    """
                )
            ).mappings().one()
            fingerprints[table] = {
                "row_count": int(row["row_count"]),
                "content_md5": row["content_md5"],
            }

        views = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT viewname, definition
                    FROM pg_views
                    WHERE schemaname = 'public'
                    ORDER BY viewname
                    """
                )
            ).mappings()
        ]
        sequences = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT sequencename, data_type, start_value, min_value,
                           max_value, increment_by, cycle, cache_size, last_value
                    FROM pg_sequences
                    WHERE schemaname = 'public'
                    ORDER BY sequencename
                    """
                )
            ).mappings()
        ]
        for row in sequences:
            state = connection.execute(
                text(f"SELECT last_value, is_called FROM public.{quote(row['sequencename'])}")
            ).mappings().one()
            row["state_last_value"] = state["last_value"]
            row["is_called"] = state["is_called"]
        functions = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT p.proname AS name,
                           pg_get_function_identity_arguments(p.oid) AS arguments,
                           pg_get_function_result(p.oid) AS result
                    FROM pg_proc p
                    JOIN pg_namespace n ON n.oid = p.pronamespace
                    WHERE n.nspname = 'public'
                    ORDER BY p.proname, arguments
                    """
                )
            ).mappings()
        ]
        heads = [
            row[0]
            for row in connection.execute(
                text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
            )
        ]

    structure = {
        "tables": tables,
        "views": views,
        "sequences": sequences,
        "functions": functions,
    }
    structure_sha256 = hashlib.sha256(
        json.dumps(
            structure,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "table_count": len(tables),
        "view_count": len(views),
        "sequence_count": len(sequences),
        "function_count": len(functions),
        "alembic_heads": heads,
        "structure_sha256": structure_sha256,
        "table_fingerprints": fingerprints,
        "sequences": sequences,
    }


def _schema_snapshot(engine: Engine, schema: str) -> dict[str, Any]:
    schema = validate_isolated_identifier(schema, kind="测试 Schema")
    with engine.connect() as connection:
        inspector = inspect(connection)
        quote = connection.dialect.identifier_preparer.quote
        tables = sorted(inspector.get_table_names(schema=schema))
        fingerprints: dict[str, dict[str, Any]] = {}
        for table in tables:
            row = connection.execute(
                text(
                    f"""
                    SELECT count(*)::bigint AS row_count,
                           md5(COALESCE(string_agg(
                               to_jsonb(t)::text,
                               E'\\n' ORDER BY to_jsonb(t)::text
                           ), '')) AS content_md5
                    FROM {quote(schema)}.{quote(table)} AS t
                    """
                )
            ).mappings().one()
            fingerprints[table] = {
                "row_count": int(row["row_count"]),
                "content_md5": row["content_md5"],
            }
        sequences = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT sequencename, last_value
                    FROM pg_sequences
                    WHERE schemaname = :schema
                    ORDER BY sequencename
                    """
                ),
                {"schema": schema},
            ).mappings()
        ]
        views = sorted(inspector.get_view_names(schema=schema))
    return {
        "table_count": len(tables),
        "view_count": len(views),
        "sequence_count": len(sequences),
        "table_fingerprints": fingerprints,
        "sequences": sequences,
    }


def _seed_controlled_business_fixtures(runtime_url: str) -> dict[str, Any]:
    """Create minimal, synthetic facts required by legacy read-contract tests."""

    generated_at = datetime(2020, 1, 1, 0, 0, 0)
    run_id = "run_day3_isolated_fixture_001"
    model_version = "day3-isolated-model-v1"
    feature_version = "day3-isolated-features-v1"
    market_rows = []
    load_rows = []
    weather_rows = []
    forecast_rows = []
    for hour in range(24):
        stamp = generated_at + timedelta(hours=hour)
        price = 80.0 + float(hour * 2)
        risk_probability = 0.65 if hour in {17, 18, 19} else 0.1
        forecast_load = 900.0 + float(hour * 5)
        forecast_rows.append(
            {
                "run_id": run_id,
                "stamp": stamp,
                "price": price,
                "risk_level": "high" if risk_probability >= 0.5 else "low",
                "risk_probability": risk_probability,
                "forecast_load": forecast_load,
                "source_row": hour + 1,
                "model_version": model_version,
                "feature_version": feature_version,
                "generated_at": generated_at,
            }
        )
        market_rows.append(
            {
                "market": "DOM",
                "node_name": "DAY3-ISOLATED",
                "stamp": stamp,
                "price": price,
                "source_row": hour + 1,
                "raw_json": json.dumps(
                    {"fixture": "day3-isolated", "hour": hour},
                    ensure_ascii=False,
                ),
            }
        )
        load_rows.append(
            {
                "market": "DOM",
                "stamp": stamp,
                "actual_load": forecast_load - 5.0,
                "forecast_load": forecast_load,
                "source_row": hour + 1,
                "raw_json": json.dumps(
                    {"fixture": "day3-isolated", "hour": hour},
                    ensure_ascii=False,
                ),
            }
        )
        weather_rows.append(
            {
                "point_name": "DAY3-ISOLATED",
                "city": "TEST",
                "stamp": stamp,
                "temperature": 10.0 + hour / 2,
                "humidity": 50.0,
                "wind_speed": 3.0,
                "source_row": hour + 1,
                "raw_json": json.dumps(
                    {"fixture": "day3-isolated", "hour": hour},
                    ensure_ascii=False,
                ),
            }
        )

    engine = create_engine(runtime_url, pool_pre_ping=True, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO forecast_runs (
                        run_id, status, domain, target_name,
                        forecast_start_at, forecast_end_at,
                        input_start_at, input_end_at,
                        model_id, model_version, artifact_id, artifact_hash,
                        feature_version, schema_hash, input_hash, result_hash,
                        source_type, started_at, finished_at, record_count,
                        source_path, forecast_start, forecast_end, generated_at,
                        row_count, summary_json
                    ) VALUES (
                        :run_id, 'success', 'electricity_day_ahead_price', 'da_price',
                        :forecast_start, :forecast_end,
                        :input_start, :input_end,
                        'day3-isolated-model', :model_version,
                        'day3-isolated-artifact', 'day3-isolated-artifact-hash',
                        :feature_version, 'day3-isolated-schema-hash',
                        'day3-isolated-input-hash', 'day3-isolated-result-hash',
                        'controlled_test_fixture', :started_at, :finished_at, 24,
                        'tests/day3_isolated_fixture', :forecast_start, :forecast_end,
                        :finished_at, 24, CAST(:summary_json AS jsonb)
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "forecast_start": generated_at,
                    "forecast_end": generated_at + timedelta(hours=23),
                    "input_start": generated_at - timedelta(days=1),
                    "input_end": generated_at - timedelta(hours=1),
                    "model_version": model_version,
                    "feature_version": feature_version,
                    "started_at": generated_at - timedelta(minutes=1),
                    "finished_at": generated_at,
                    "summary_json": json.dumps(
                        {"fixture": "day3-isolated", "record_count": 24},
                        ensure_ascii=False,
                    ),
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO forecast_results (
                        run_id, forecast_datetime, forecast_time,
                        predicted_price, corrected_predicted_price,
                        risk_level, spike_risk_prob, forecast_load,
                        source_row, model_version, feature_version,
                        generated_at, base_prediction, peak_prediction,
                        classifier_prediction, p90_prediction,
                        blend_weight, adjustment, source_type
                    ) VALUES (
                        :run_id, :stamp, :stamp,
                        :price, :price,
                        :risk_level, :risk_probability, :forecast_load,
                        :source_row, :model_version, :feature_version,
                        :generated_at, :price, :price,
                        :risk_probability, :price,
                        1.0, 0.0, 'controlled_test_fixture'
                    )
                    """
                ),
                forecast_rows,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO raw_market (
                        market, node_name, price_type, datetime,
                        da_price, source_file, source_row, raw_json
                    ) VALUES (
                        :market, :node_name, 'DA', :stamp,
                        :price, 'day3_isolated_fixture', :source_row,
                        CAST(:raw_json AS jsonb)
                    )
                    """
                ),
                market_rows,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO raw_load (
                        market, datetime, actual_load, forecast_load,
                        source_file, source_row, raw_json
                    ) VALUES (
                        :market, :stamp, :actual_load, :forecast_load,
                        'day3_isolated_fixture', :source_row,
                        CAST(:raw_json AS jsonb)
                    )
                    """
                ),
                load_rows,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO raw_weather (
                        point_name, city, datetime, temperature, humidity,
                        wind_speed, source_file, source_row, raw_json
                    ) VALUES (
                        :point_name, :city, :stamp, :temperature, :humidity,
                        :wind_speed, 'day3_isolated_fixture', :source_row,
                        CAST(:raw_json AS jsonb)
                    )
                    """
                ),
                weather_rows,
            )
    finally:
        engine.dispose()
    return {
        "fixture_id": "day3-isolated-business-v1",
        "run_id": run_id,
        "forecast_runs": 1,
        "forecast_results": 24,
        "raw_market": 24,
        "raw_load": 24,
        "raw_weather": 24,
        "generated_at": generated_at.isoformat(),
        "contains_real_business_records": False,
    }


def _snapshot_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_tables = before["table_fingerprints"]
    after_tables = after["table_fingerprints"]
    names = sorted(set(before_tables) | set(after_tables))
    changed_tables = {
        name: {"before": before_tables.get(name), "after": after_tables.get(name)}
        for name in names
        if before_tables.get(name) != after_tables.get(name)
    }
    before_sequences = {row["sequencename"]: row for row in before["sequences"]}
    after_sequences = {row["sequencename"]: row for row in after["sequences"]}
    sequence_names = sorted(set(before_sequences) | set(after_sequences))
    changed_sequences = {
        name: {"before": before_sequences.get(name), "after": after_sequences.get(name)}
        for name in sequence_names
        if before_sequences.get(name) != after_sequences.get(name)
    }
    return {
        "changed_tables": changed_tables,
        "changed_sequences": changed_sequences,
    }


def _create_isolation_objects(engine: Engine, schema: str, role: str) -> None:
    schema_sql = _quote_identifier(schema)
    role_sql = _quote_identifier(role)
    with engine.begin() as connection:
        existing_schema = connection.execute(
            text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"),
            {"schema": schema},
        ).scalar_one_or_none()
        existing_role = connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
            {"role": role},
        ).scalar_one_or_none()
        if existing_schema or existing_role:
            raise DatabaseIsolationError("拒绝复用已有隔离 Schema 或角色")
        connection.execute(
            text(
                f"""
                CREATE ROLE {role_sql}
                NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                NOINHERIT NOREPLICATION NOBYPASSRLS
                """
            )
        )
        connection.execute(text(f"CREATE SCHEMA {schema_sql} AUTHORIZATION {role_sql}"))
        connection.execute(text(f"REVOKE ALL ON SCHEMA public FROM {role_sql}"))
        connection.execute(
            text(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {role_sql}")
        )
        connection.execute(
            text(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {role_sql}")
        )
        connection.execute(
            text(f"REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM {role_sql}")
        )


def _cleanup_isolation_objects(engine: Engine, schema: str, role: str) -> None:
    schema_sql = _quote_identifier(schema)
    role_sql = _quote_identifier(role)
    with engine.begin() as connection:
        owner = connection.execute(
            text(
                """
                SELECT pg_get_userbyid(nspowner)
                FROM pg_namespace
                WHERE nspname = :schema
                """
            ),
            {"schema": schema},
        ).scalar_one_or_none()
        if owner is not None and owner != role:
            raise DatabaseIsolationError("拒绝清理 owner 不匹配的 Schema")
        if owner == role:
            connection.execute(text(f"DROP SCHEMA {schema_sql} CASCADE"))
        role_exists = connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
            {"role": role},
        ).scalar_one_or_none()
        if role_exists:
            connection.execute(text(f"DROP ROLE {role_sql}"))


def _residual_objects(engine: Engine, schema: str, role: str) -> dict[str, list[str]]:
    with engine.connect() as connection:
        schemas = [
            row[0]
            for row in connection.execute(
                text("SELECT nspname FROM pg_namespace WHERE nspname = :schema"),
                {"schema": schema},
            )
        ]
        roles = [
            row[0]
            for row in connection.execute(
                text("SELECT rolname FROM pg_roles WHERE rolname = :role"),
                {"role": role},
            )
        ]
    return {"schemas": schemas, "roles": roles}


def _run_alembic(base_url: str, schema: str, role: str, project_root: Path) -> None:
    parsed = validate_database_target(base_url)
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": base_url,
            "APP_ENV": "test",
            "ALEMBIC_TARGET_SCHEMA": schema,
            "ALEMBIC_SCHEMA_PREFIX": TEST_SCHEMA_PREFIX,
            "ALEMBIC_EXECUTION_ROLE": role,
            "ALEMBIC_EXPECTED_DATABASE": EXPECTED_DATABASE,
            "ALEMBIC_EXPECTED_HOST": parsed.host or "",
            "ALEMBIC_EXPECTED_PORT": str(parsed.port or EXPECTED_PORT),
            "ALEMBIC_EXPECTED_USER": parsed.username or "",
        }
    )
    environment.pop("PGOPTIONS", None)
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise DatabaseIsolationError(
            f"隔离 Schema Alembic 迁移失败，退出码 {completed.returncode}"
        )


def _write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def run_isolated_command(
    command: Sequence[str],
    *,
    evidence_path: Path,
    project_root: Path,
    label: str,
) -> int:
    if not command:
        raise DatabaseIsolationError("缺少隔离测试命令")
    load_dotenv()
    base_url = os.environ.get("DATABASE_URL", "").strip()
    parsed = validate_database_target(base_url)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    schema = validate_isolated_identifier(
        f"{TEST_SCHEMA_PREFIX}{stamp}_{os.getpid()}",
        kind="测试 Schema",
    )
    role = validate_isolated_identifier(f"{schema}{TEST_ROLE_SUFFIX}", kind="测试角色")
    base_engine = create_engine(base_url, pool_pre_ping=True, future=True)
    created = False
    child_returncode: int | None = None
    error: str | None = None
    public_before: dict[str, Any] | None = None
    public_after: dict[str, Any] | None = None
    isolated_before: dict[str, Any] | None = None
    isolated_after: dict[str, Any] | None = None
    isolated_migrated: dict[str, Any] | None = None
    controlled_fixtures: dict[str, Any] | None = None
    runtime_verification: dict[str, Any] | None = None
    cleanup_error: str | None = None
    residual = {"schemas": [], "roles": []}
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        public_before = _public_snapshot(base_engine)
        _create_isolation_objects(base_engine, schema, role)
        created = True
        _run_alembic(base_url, schema, role, project_root)
        runtime_url = build_isolated_runtime_url(base_url, schema, role)
        security_runtime_url = build_isolated_security_url(runtime_url)
        runtime_verification = verify_isolated_runtime(runtime_url, schema, role)
        isolated_migrated = _schema_snapshot(base_engine, schema)
        controlled_fixtures = _seed_controlled_business_fixtures(runtime_url)
        isolated_before = _schema_snapshot(base_engine, schema)

        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": runtime_url,
                SECURITY_DATABASE_URL_ENV: security_runtime_url,
                "APP_ENV": "test",
                ISOLATION_FLAG: "1",
                SCHEMA_ENV: schema,
                ROLE_ENV: role,
                MODE_ENV: "isolated-schema",
            }
        )
        environment.pop(MIGRATION_DATABASE_URL_ENV, None)
        environment.pop("PGOPTIONS", None)
        child = subprocess.run(list(command), cwd=project_root, env=environment, check=False)
        child_returncode = child.returncode
        isolated_after = _schema_snapshot(base_engine, schema)
        public_after = _public_snapshot(base_engine)
    except Exception as exc:
        error = _safe_error(exc)
        try:
            if created and isolated_after is None:
                isolated_after = _schema_snapshot(base_engine, schema)
        except Exception:
            pass
        try:
            if public_before is not None and public_after is None:
                public_after = _public_snapshot(base_engine)
        except Exception:
            pass
    finally:
        if created:
            try:
                _cleanup_isolation_objects(base_engine, schema, role)
            except Exception as exc:
                cleanup_error = _safe_error(exc)
        try:
            residual = _residual_objects(base_engine, schema, role)
        except Exception as exc:
            cleanup_error = cleanup_error or _safe_error(exc)
        base_engine.dispose()

    public_match = public_before is not None and public_before == public_after
    cleanup_pass = not cleanup_error and not residual["schemas"] and not residual["roles"]
    command_pass = child_returncode == 0
    result = (
        "PASS"
        if error is None and command_pass and public_match and cleanup_pass
        else "FAIL"
    )
    evidence = {
        "label": label,
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "command": list(command),
        "command_returncode": child_returncode,
        "target": _target_summary(parsed),
        "schema": schema,
        "role": role,
        "runtime_verification": runtime_verification,
        "public_before": public_before,
        "public_after": public_after,
        "public_match": public_match,
        "controlled_fixtures": controlled_fixtures,
        "isolated_migrated": isolated_migrated,
        "isolated_before": isolated_before,
        "isolated_after": isolated_after,
        "fixture_changes": (
            _snapshot_delta(isolated_migrated, isolated_before)
            if isolated_migrated is not None and isolated_before is not None
            else None
        ),
        "isolated_changes": (
            _snapshot_delta(isolated_before, isolated_after)
            if isolated_before is not None and isolated_after is not None
            else None
        ),
        "cleanup": {
            "result": "PASS" if cleanup_pass else "FAIL",
            "residual": residual,
            "error": cleanup_error,
        },
        "error": error,
    }
    _write_evidence(evidence_path, evidence)
    print(
        json.dumps(
            {
                "result": result,
                "schema": schema,
                "role": role,
                "command_returncode": child_returncode,
                "public_match": public_match,
                "cleanup": evidence["cleanup"],
                "changed_isolated_tables": sorted(
                    (evidence["isolated_changes"] or {}).get("changed_tables", {})
                ),
                "changed_isolated_sequences": sorted(
                    (evidence["isolated_changes"] or {}).get("changed_sequences", {})
                ),
                "evidence": str(evidence_path),
                "error": error,
            },
            ensure_ascii=False,
        )
    )
    return 0 if result == "PASS" else (child_returncode or 1)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a command in a restricted beta10d Day 3 PostgreSQL Schema."
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--label", default="day3-isolated-test")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    try:
        return run_isolated_command(
            args.command,
            evidence_path=args.evidence.resolve(),
            project_root=project_root,
            label=args.label,
        )
    except Exception as exc:
        print(json.dumps({"result": "FAIL", "error": _safe_error(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
