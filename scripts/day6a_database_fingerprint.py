from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.redaction import mask_secret_fields, safe_exception_summary


ConnectFactory = Callable[..., Any]
SOURCE_TABLES = ("raw_market", "raw_load", "raw_weather", "raw_renewable")
TIME_COLUMNS = ("datetime", "timestamp", "data_time", "forecast_time", "date_time")


def _connection_metadata(url: URL) -> dict[str, Any]:
    return {
        "driver": url.drivername,
        "host": url.host or "",
        "port": url.port or 5432,
        "user": url.username or "",
        "database": url.database or "",
        "password": "******" if url.password else "",
    }


def _connection_kwargs(url: URL) -> dict[str, Any]:
    values: dict[str, Any] = {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "dbname": url.database or "postgres",
        "user": url.username or "",
        "password": url.password or "",
        "connect_timeout": 5,
        "autocommit": False,
    }
    if url.query.get("sslmode"):
        values["sslmode"] = url.query["sslmode"]
    return values


def _schema_rows(cursor: Any) -> list[tuple[Any, ...]]:
    cursor.execute(
        """
        SELECT table_name, column_name, ordinal_position, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    columns = cursor.fetchall()
    cursor.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
        """
    )
    indexes = cursor.fetchall()
    return [("column", *row) for row in columns] + [("index", *row) for row in indexes]


def _source_watermarks(cursor: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for table in SOURCE_TABLES:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        columns = [str(row[0]) for row in cursor.fetchall()]
        if not columns:
            result.append({"table": table, "exists": False})
            continue
        time_column = next((name for name in TIME_COLUMNS if name in columns), None)
        query = sql.SQL("SELECT count(*)")
        if time_column:
            query += sql.SQL(", max({})::text").format(sql.Identifier(time_column))
        query += sql.SQL(" FROM {}").format(sql.Identifier(table))
        cursor.execute(query)
        row = cursor.fetchone()
        result.append(
            {
                "table": table,
                "exists": True,
                "rows": int(row[0]),
                "time_column": time_column,
                "max_time": row[1] if time_column else None,
            }
        )
    return result


def _collect(cursor: Any) -> dict[str, Any]:
    cursor.execute("SELECT current_user, current_database()")
    current_user, current_database = cursor.fetchone()
    cursor.execute("SELECT version_num FROM alembic_version")
    alembic = sorted(str(row[0]) for row in cursor.fetchall())
    cursor.execute(
        """
        SELECT
          (SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'),
          (SELECT count(*) FROM information_schema.views WHERE table_schema='public'),
          (SELECT count(*) FROM information_schema.sequences WHERE sequence_schema='public'),
          (SELECT count(*) FROM information_schema.routines WHERE routine_schema='public')
        """
    )
    tables, views, sequences, routines = cursor.fetchone()
    cursor.execute(
        "SELECT to_jsonb(m) - 'artifact_path' FROM model_registry m WHERE status='active' ORDER BY 1::text"
    )
    active_models = [row[0] for row in cursor.fetchall()]
    schema_rows = _schema_rows(cursor)
    schema_hash = hashlib.sha256(
        json.dumps(schema_rows, ensure_ascii=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "identity": {"current_user": current_user, "current_database": current_database},
        "alembic_heads": alembic,
        "object_counts": {
            "tables": int(tables),
            "views": int(views),
            "sequences": int(sequences),
            "routines": int(routines),
        },
        "schema_sha256": schema_hash,
        "active_models": active_models,
        "source_watermarks": _source_watermarks(cursor),
    }


def build_fingerprint(database_url: str, *, connect_factory: ConnectFactory | None = None) -> dict[str, Any]:
    connect_factory = connect_factory or psycopg.connect
    secret = ""
    try:
        url = make_url(database_url)
        secret = url.password or ""
        metadata = _connection_metadata(url)
        connection_kwargs = _connection_kwargs(url)
    except Exception as exc:
        return {
            "status": "failed",
            "stage": "parse_database_url",
            "error": safe_exception_summary(exc),
        }
    report: dict[str, Any] = {"status": "failed", "connection": metadata}
    try:
        with connect_factory(**connection_kwargs) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                report["fingerprint"] = _collect(cursor)
                connection.rollback()
        report["status"] = "pass"
        return mask_secret_fields(report)
    except Exception as exc:
        report.update(
            {
                "status": "failed",
                "stage": "database_fingerprint",
                "error": safe_exception_summary(exc, extra_secrets=(secret,)),
            }
        )
        return mask_secret_fields(report)


def write_json(report: dict[str, Any], output: Path) -> None:
    safe = mask_secret_fields(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(safe, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_markdown(report: dict[str, Any], output: Path) -> None:
    safe = mask_secret_fields(report)
    connection = safe.get("connection") or {}
    lines = [
        "# Day 6A read-only database fingerprint",
        "",
        f"- status: `{safe.get('status')}`",
        f"- stage: `{safe.get('stage', 'complete')}`",
        f"- connection: host={connection.get('host', '')} port={connection.get('port', '')} "
        f"user={connection.get('user', '')} database={connection.get('database', '')} password=******",
        "",
        "```json",
        json.dumps(safe, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a read-only, credential-redacted PostgreSQL fingerprint.")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        report = {"status": "failed", "stage": "configuration", "error": {"error_type": "MissingDatabaseUrl"}}
    else:
        report = build_fingerprint(database_url)
    if args.json:
        write_json(report, args.json)
    if args.markdown:
        write_markdown(report, args.markdown)
    print(json.dumps(mask_secret_fields(report), ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
