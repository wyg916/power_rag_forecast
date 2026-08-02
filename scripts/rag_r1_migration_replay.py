from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, make_url, text
from sqlalchemy.engine import Engine, URL


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PREFIX = "beta10d_rag_r1_"
ROLE_SUFFIX = "_role"
EXPECTED = {
    "host": "localhost",
    "port": 5432,
    "database": "postgres",
    "user": "postgres",
}
HEAD_REVISION = "0018_rag_enterprise_r1"
DOWN_REVISION = "0017_day6_operational"
ENTERPRISE_TABLES = {
    "kb_document_versions",
    "kb_assets",
    "kb_access_policies",
    "kb_releases",
    "kb_release_items",
    "kb_retrieval_runs",
    "kb_citations",
    "kb_qa_evaluations",
    "kb_rag_audit_events",
}
HEAD_COLUMNS = {
    "kb_documents": {"tenant_id", "domain", "owner_actor_id"},
    "kb_chunks": {
        "tenant_id",
        "version_id",
        "parent_chunk_id",
        "chunk_level",
        "section_path_json",
        "locator_json",
        "content_sha256",
        "token_count",
        "embedding_provider",
        "embedding_model",
        "embedding_version",
        "embedding_dimension",
        "embedding_status",
    },
    "kb_search_results": {"tenant_id", "release_id", "run_id", "trace_id"},
    "kb_qa_tests": {"tenant_id", "release_id", "run_id", "trace_id"},
    "audit_logs": {"tenant_id", "release_id", "run_id", "trace_id"},
}
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_SECRET_URL_RE = re.compile(
    r"(postgres(?:ql)?(?:\+\w+)?://[^:\s/@]+:)[^@\s]+(@)", re.IGNORECASE
)


class MigrationReplayError(RuntimeError):
    pass


def _safe(value: object) -> str:
    return _SECRET_URL_RE.sub(r"\1***\2", str(value))


def _load_url(env_file: Path) -> URL:
    values = dotenv_values(env_file)
    raw = str(values.get("MIGRATION_DATABASE_URL") or values.get("DATABASE_URL") or "")
    if not raw:
        raise MigrationReplayError("database_url_missing")
    url = make_url(raw)
    actual = {
        "host": url.host or "",
        "port": url.port or 5432,
        "database": url.database or "",
        "user": url.username or "",
    }
    if actual != EXPECTED:
        raise MigrationReplayError(f"database_target_rejected:{actual}")
    return url


def _validate_identifier(value: str, *, role: bool = False) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise MigrationReplayError("isolated_identifier_rejected")
    if not value.startswith(SCHEMA_PREFIX) or value == "public":
        raise MigrationReplayError("isolated_prefix_rejected")
    if role and not value.endswith(ROLE_SUFFIX):
        raise MigrationReplayError("isolated_role_suffix_rejected")
    return value


def _quote(value: str) -> str:
    return f'"{_validate_identifier(value, role=value.endswith(ROLE_SUFFIX))}"'


def _make_names() -> tuple[str, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    schema = _validate_identifier(f"{SCHEMA_PREFIX}{stamp}_{os.getpid()}")
    role = _validate_identifier(f"{schema}{ROLE_SUFFIX}", role=True)
    return schema, role


def _engine(url: URL) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        future=True,
        connect_args={"hostaddr": "127.0.0.1", "connect_timeout": 5},
    )


def _create_isolation(engine: Engine, schema: str, role: str) -> None:
    schema_sql, role_sql = _quote(schema), _quote(role)
    with engine.begin() as connection:
        exists = connection.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:schema), "
                "EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"
            ),
            {"schema": schema, "role": role},
        ).one()
        if any(exists):
            raise MigrationReplayError("isolated_objects_already_exist")
        connection.execute(
            text(
                f"CREATE ROLE {role_sql} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOINHERIT NOREPLICATION NOBYPASSRLS"
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


def _cleanup_isolation(engine: Engine, schema: str, role: str) -> None:
    schema_sql, role_sql = _quote(schema), _quote(role)
    with engine.begin() as connection:
        owner = connection.execute(
            text(
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace "
                "WHERE nspname=:schema"
            ),
            {"schema": schema},
        ).scalar_one_or_none()
        if owner is not None and owner != role:
            raise MigrationReplayError("isolated_schema_owner_mismatch")
        if owner == role:
            connection.execute(text(f"DROP SCHEMA {schema_sql} CASCADE"))
        if connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}
        ).scalar_one_or_none():
            connection.execute(text(f"DROP ROLE {role_sql}"))


def _residual(engine: Engine, schema: str, role: str) -> dict[str, bool]:
    with engine.connect() as connection:
        return {
            "schema": bool(
                connection.execute(
                    text("SELECT 1 FROM pg_namespace WHERE nspname=:name"),
                    {"name": schema},
                ).scalar_one_or_none()
            ),
            "role": bool(
                connection.execute(
                    text("SELECT 1 FROM pg_roles WHERE rolname=:name"),
                    {"name": role},
                ).scalar_one_or_none()
            ),
        }


def _catalog(engine: Engine, schema: str) -> dict[str, Any]:
    if schema != "public":
        _validate_identifier(schema)
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables = sorted(inspector.get_table_names(schema=schema))
        columns = {
            table: [
                {
                    "name": str(item["name"]),
                    "type": str(item["type"]),
                    "nullable": bool(item["nullable"]),
                    "default": str(item.get("default") or ""),
                }
                for item in inspector.get_columns(table, schema=schema)
            ]
            for table in tables
        }
        constraints = {
            table: {
                "pk": inspector.get_pk_constraint(table, schema=schema),
                "fk": inspector.get_foreign_keys(table, schema=schema),
                "unique": inspector.get_unique_constraints(table, schema=schema),
                "check": inspector.get_check_constraints(table, schema=schema),
            }
            for table in tables
        }
        indexes = {
            table: inspector.get_indexes(table, schema=schema) for table in tables
        }
        version = None
        if "alembic_version" in tables:
            version = connection.execute(
                text(f"SELECT version_num FROM \"{schema}\".alembic_version")
            ).scalar_one_or_none()
    payload = {
        "tables": tables,
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "alembic_revision": version,
    }
    payload["structure_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def _assert_head(catalog: dict[str, Any]) -> None:
    tables = set(catalog["tables"])
    if catalog["alembic_revision"] != HEAD_REVISION:
        raise MigrationReplayError("head_revision_mismatch")
    missing_tables = sorted(ENTERPRISE_TABLES - tables)
    if missing_tables:
        raise MigrationReplayError(f"head_tables_missing:{missing_tables}")
    for table, expected in HEAD_COLUMNS.items():
        actual = {item["name"] for item in catalog["columns"].get(table, [])}
        missing = sorted(expected - actual)
        if missing:
            raise MigrationReplayError(f"head_columns_missing:{table}:{missing}")


def _assert_down(catalog: dict[str, Any]) -> None:
    if catalog["alembic_revision"] != DOWN_REVISION:
        raise MigrationReplayError("down_revision_mismatch")
    remaining_tables = sorted(ENTERPRISE_TABLES & set(catalog["tables"]))
    if remaining_tables:
        raise MigrationReplayError(f"down_tables_remaining:{remaining_tables}")
    for table, added in HEAD_COLUMNS.items():
        actual = {item["name"] for item in catalog["columns"].get(table, [])}
        remaining = sorted(added & actual)
        if remaining:
            raise MigrationReplayError(f"down_columns_remaining:{table}:{remaining}")


def _alembic_environment(url: URL, schema: str, role: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": url.render_as_string(hide_password=False),
            "MIGRATION_DATABASE_URL": "",
            "APP_ENV": "test",
            "ALEMBIC_TARGET_SCHEMA": schema,
            "ALEMBIC_SCHEMA_PREFIX": SCHEMA_PREFIX,
            "ALEMBIC_EXECUTION_ROLE": role,
            "ALEMBIC_EXPECTED_DATABASE": EXPECTED["database"],
            "ALEMBIC_EXPECTED_HOST": EXPECTED["host"],
            "ALEMBIC_EXPECTED_PORT": str(EXPECTED["port"]),
            "ALEMBIC_EXPECTED_USER": EXPECTED["user"],
        }
    )
    environment.pop("PGOPTIONS", None)
    return environment


def _run_alembic(
    url: URL, schema: str, role: str, arguments: Sequence[str]
) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=PROJECT_ROOT,
        env=_alembic_environment(url, schema, role),
        check=False,
        capture_output=True,
        text=True,
    )
    record = {
        "arguments": list(arguments),
        "returncode": completed.returncode,
        "stdout": _safe(completed.stdout)[-4000:],
        "stderr": _safe(completed.stderr)[-4000:],
    }
    if completed.returncode:
        raise MigrationReplayError(
            f"alembic_failed:{' '.join(arguments)}:{completed.returncode}:"
            f"{record['stderr'][-1000:]}"
        )
    return record


def run_replay(env_file: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise MigrationReplayError("output_directory_not_empty")
    output.mkdir(parents=True, exist_ok=True)
    url = _load_url(env_file)
    schema, role = _make_names()
    engine = _engine(url)
    created = False
    commands: list[dict[str, Any]] = []
    payload: dict[str, Any] = {
        "status": "FAILED",
        "target": EXPECTED,
        "schema": schema,
        "role": role,
        "public_write_count": 0,
    }
    try:
        public_before = _catalog(engine, "public")
        _create_isolation(engine, schema, role)
        created = True
        commands.append(_run_alembic(url, schema, role, ("upgrade", "head")))
        head_first = _catalog(engine, schema)
        _assert_head(head_first)
        commands.append(_run_alembic(url, schema, role, ("downgrade", DOWN_REVISION)))
        down = _catalog(engine, schema)
        _assert_down(down)
        commands.append(_run_alembic(url, schema, role, ("upgrade", "head")))
        head_second = _catalog(engine, schema)
        _assert_head(head_second)
        if head_first["structure_sha256"] != head_second["structure_sha256"]:
            raise MigrationReplayError("head_replay_structure_hash_mismatch")
        public_after = _catalog(engine, "public")
        if public_before["structure_sha256"] != public_after["structure_sha256"]:
            raise MigrationReplayError("public_structure_changed")
        payload.update(
            {
                "status": "PASS",
                "commands": commands,
                "public_before": {
                    "revision": public_before["alembic_revision"],
                    "structure_sha256": public_before["structure_sha256"],
                },
                "public_after": {
                    "revision": public_after["alembic_revision"],
                    "structure_sha256": public_after["structure_sha256"],
                },
                "head_first_sha256": head_first["structure_sha256"],
                "down_sha256": down["structure_sha256"],
                "head_second_sha256": head_second["structure_sha256"],
                "enterprise_table_count": len(ENTERPRISE_TABLES),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return payload
    except Exception as exc:
        payload.update({"commands": commands, "error": _safe(exc)})
        raise
    finally:
        cleanup_error = None
        try:
            if created:
                _cleanup_isolation(engine, schema, role)
            residual = _residual(engine, schema, role)
            if any(residual.values()):
                raise MigrationReplayError(f"isolated_cleanup_residual:{residual}")
        except Exception as exc:
            cleanup_error = _safe(exc)
            payload["status"] = "FAILED"
            payload["cleanup_error"] = cleanup_error
        finally:
            engine.dispose()
            payload["cleanup"] = {
                "schema_removed": not residual.get("schema", True)
                if "residual" in locals()
                else False,
                "role_removed": not residual.get("role", True)
                if "residual" in locals()
                else False,
            }
            (output / "migration_replay.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
        if cleanup_error and sys.exc_info()[0] is None:
            raise MigrationReplayError(cleanup_error)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG-R1 isolated Alembic replay")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_replay(args.env_file.resolve(), args.output.resolve())
    except Exception as exc:
        print(f"RAG-R1 migration replay FAILED: {_safe(exc)}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
