from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from scripts.day3_test_database_guard import _public_snapshot


EXPECTED = {
    "host": "localhost",
    "port": 5432,
    "database": "postgres",
    "user": "postgres",
}
RAG_TABLES = (
    "kb_documents",
    "kb_document_versions",
    "kb_chunks",
    "kb_assets",
    "kb_access_policies",
    "kb_releases",
    "kb_release_items",
    "kb_retrieval_runs",
    "kb_citations",
    "kb_qa_evaluations",
    "kb_rag_audit_events",
    "kb_search_results",
    "kb_qa_tests",
    "audit_logs",
)


def _load_url(env_file: Path):
    values = dotenv_values(env_file)
    raw = str(values.get("MIGRATION_DATABASE_URL") or values.get("DATABASE_URL") or "")
    if not raw:
        raise RuntimeError("database_url_missing")
    url = make_url(raw)
    actual = {
        "host": url.host or "",
        "port": url.port or 5432,
        "database": url.database or "",
        "user": url.username or "",
    }
    if actual != EXPECTED:
        raise RuntimeError(f"database_target_rejected:{actual}")
    return url


def _catalog(connection) -> dict[str, Any]:
    columns = [
        dict(row)
        for row in connection.execute(
            text(
                """
                SELECT table_name, column_name, ordinal_position, data_type,
                       udt_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
        ).mappings()
    ]
    constraints = [
        dict(row)
        for row in connection.execute(
            text(
                """
                SELECT c.conname AS name, c.contype AS type,
                       rel.relname AS table_name,
                       pg_get_constraintdef(c.oid, true) AS definition
                FROM pg_constraint c
                JOIN pg_class rel ON rel.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = rel.relnamespace
                WHERE n.nspname = 'public'
                ORDER BY rel.relname, c.conname
                """
            )
        ).mappings()
    ]
    indexes = [
        dict(row)
        for row in connection.execute(
            text(
                """
                SELECT tablename AS table_name, indexname AS name, indexdef AS definition
                FROM pg_indexes
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname
                """
            )
        ).mappings()
    ]
    return {"columns": columns, "constraints": constraints, "indexes": indexes}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_snapshot(env_file: Path, output: Path, label: str) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"snapshot_output_not_empty:{output}")
    output.mkdir(parents=True, exist_ok=True)
    url = _load_url(env_file)
    engine = create_engine(
        url,
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
            identity = dict(
                connection.execute(
                    text(
                        """
                        SELECT current_database() AS database,
                               current_user AS current_user,
                               inet_server_addr()::text AS server_address,
                               inet_server_port() AS server_port,
                               current_setting('transaction_read_only') AS transaction_read_only
                        """
                    )
                ).mappings().one()
            )
            if identity["transaction_read_only"] != "on":
                raise RuntimeError("snapshot_transaction_not_read_only")
            catalog = _catalog(connection)
            connection.rollback()
        public = _public_snapshot(engine)
    finally:
        engine.dispose()

    rag_counts = {
        table: public["table_fingerprints"][table]["row_count"]
        for table in RAG_TABLES
        if table in public["table_fingerprints"]
    }
    report = {
        "label": label,
        "target": EXPECTED,
        "connection_identity": identity,
        "public": public,
        "catalog": catalog,
        "rag_row_counts": rag_counts,
        "database_write_count": 0,
    }
    snapshot_path = output / "public_database_snapshot.json"
    snapshot_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    summary_path = output / "SUMMARY.md"
    summary_path.write_text(
        "\n".join(
            [
                f"# {label}",
                "",
                "- 目标：`localhost:5432/postgres`，用户 `postgres`。",
                "- 事务：`READ ONLY`；数据库写入：0。",
                f"- Alembic：`{', '.join(public['alembic_heads'])}`。",
                f"- public 对象：{public['table_count']} tables / {public['view_count']} views / "
                f"{public['sequence_count']} sequences / {public['function_count']} functions。",
                f"- public structure SHA-256：`{public['structure_sha256']}`。",
                f"- RAG 行数：`{json.dumps(rag_counts, ensure_ascii=False, sort_keys=True)}`。",
                "- 恢复：代码使用逐提交 `git revert`；正式 migration 若需回滚，先恢复本快照对应的业务备份，"
                "再在无新增 RAG 事实时执行 `alembic downgrade 0017_day6_operational`。",
                "- 本快照不含密码、连接串、模型路径或业务正文。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    checksum_path = output / "CHECKSUMS.sha256"
    checksum_path.write_text(
        f"{_sha256(snapshot_path)} *{snapshot_path.name}\n"
        f"{_sha256(summary_path)} *{summary_path.name}\n",
        encoding="ascii",
    )
    return {
        "output": str(output),
        "alembic_heads": public["alembic_heads"],
        "structure_sha256": public["structure_sha256"],
        "rag_row_counts": rag_counts,
        "database_write_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a read-only RAG-R1 PostgreSQL checkpoint.")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            create_snapshot(args.env_file, args.output, args.label),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
