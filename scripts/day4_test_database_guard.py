from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db.session import validate_runtime_database_roles
from backend.app.services.dataset_query_service import query_dataset_rows, validate_registry_against_database
from scripts.day3_test_database_guard import _public_snapshot, _snapshot_delta


def _read_urls(path: Path) -> tuple[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    runtime = values.get("DATABASE_URL", "")
    security = values.get("SECURITY_DATABASE_URL", "")
    if not runtime or not security:
        raise RuntimeError("Day 4 本地配置缺少运行或安全连接。")
    return runtime, security


def _role_summary(engine) -> dict[str, Any]:
    with engine.connect() as conn:
        return dict(
            conn.execute(
                text(
                    """
                    SELECT current_user AS role_name, r.rolsuper, r.rolcreatedb,
                           r.rolcreaterole, r.rolreplication, r.rolbypassrls,
                           has_database_privilege(current_user, current_database(), 'CREATE') AS database_create,
                           has_schema_privilege(current_user, 'public', 'CREATE') AS schema_create
                    FROM pg_roles r WHERE r.rolname = current_user
                    """
                )
            ).mappings().one()
        )


def _expect_success(engine, statement: str, params: dict[str, Any] | None = None) -> None:
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text(statement), params or {})
        finally:
            transaction.rollback()


def _expect_rejected(engine, statement: str) -> str:
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text(statement))
        except DBAPIError as exc:
            transaction.rollback()
            return type(exc.orig).__name__
        transaction.rollback()
    raise AssertionError("禁止操作被数据库接受。")


def run_guard(migration_url: str, runtime_url: str, security_url: str, baseline_path: Path) -> dict[str, Any]:
    migration_engine = create_engine(migration_url, pool_pre_ping=True, future=True)
    runtime_engine = create_engine(runtime_url, pool_pre_ping=True, future=True)
    security_engine = create_engine(security_url, pool_pre_ping=True, future=True)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["public"]
    role_gate = validate_runtime_database_roles(runtime_engine, security_engine)
    registry_gate = validate_registry_against_database(runtime_engine)

    allowed: dict[str, str] = {}
    query = query_dataset_rows("day_ahead_price", page=1, page_size=2, engine=runtime_engine)
    if query["dataset_id"] != "day_ahead_price" or len(query["records"]) > 2:
        raise AssertionError("受控数据集读取未通过分页边界。")
    allowed["registered_dataset_select"] = "pass"
    _expect_success(runtime_engine, "UPDATE public.raw_market SET market = market WHERE false")
    allowed["business_update"] = "pass_rolled_back"
    _expect_success(runtime_engine, "DELETE FROM public.raw_market WHERE false")
    allowed["business_delete"] = "pass_rolled_back"
    _expect_success(
        runtime_engine,
        """
        INSERT INTO public.audit_logs
            (id, actor, role_id, action, resource_type, resource_id, status)
        VALUES
            (-9223372036854775807, 'day4_guard', 'guard', 'day4.guard', 'guard', 'rollback', 'success')
        """,
    )
    allowed["audit_insert"] = "pass_rolled_back_without_sequence_use"
    _expect_success(security_engine, "SELECT username, password_hash FROM public.users LIMIT 1")
    allowed["security_auth_select"] = "pass"
    _expect_success(security_engine, "SELECT id, action FROM public.audit_logs LIMIT 1")
    allowed["security_audit_select"] = "pass"

    denied_statements = {
        "runtime_users": "SELECT username, password_hash FROM public.users LIMIT 1",
        "runtime_audit": "SELECT id, action FROM public.audit_logs LIMIT 1",
        "runtime_alembic": "SELECT version_num FROM public.alembic_version",
        "runtime_pg_authid": "SELECT rolname FROM pg_authid LIMIT 1",
        "runtime_server_file": "SELECT pg_read_file('postgresql.conf', 0, 1)",
        "runtime_schema_ddl": "CREATE TABLE public.beta10d_day4_forbidden_probe (id integer)",
        "runtime_create_role": "CREATE ROLE beta10d_day4_forbidden_probe_role",
        "security_business_data": "SELECT * FROM public.raw_market LIMIT 1",
    }
    denied = {name: _expect_rejected(runtime_engine if name.startswith("runtime_") else security_engine, sql_text) for name, sql_text in denied_statements.items()}

    after = _public_snapshot(migration_engine)
    delta = _snapshot_delta(baseline, after)
    structure_changed = any(
        baseline[key] != after[key]
        for key in ("table_count", "view_count", "sequence_count", "function_count", "alembic_heads", "structure_sha256")
    )
    if structure_changed or delta["changed_tables"] or delta["changed_sequences"]:
        raise AssertionError("Day 4 ACL 验证改变了 public 结构、内容或序列状态。")
    return {
        "status": "PASS",
        "target": {
            "database": make_url(migration_url).database,
            "host": make_url(migration_url).host,
            "port": make_url(migration_url).port or 5432,
        },
        "roles": {
            "runtime": _role_summary(runtime_engine),
            "security": _role_summary(security_engine),
            "validation": role_gate,
        },
        "registry": registry_gate,
        "allowed": allowed,
        "denied": denied,
        "public_before": {
            "table_count": baseline["table_count"],
            "view_count": baseline["view_count"],
            "sequence_count": baseline["sequence_count"],
            "function_count": baseline["function_count"],
            "alembic_heads": baseline["alembic_heads"],
            "structure_sha256": baseline["structure_sha256"],
        },
        "public_after": {
            "table_count": after["table_count"],
            "view_count": after["view_count"],
            "sequence_count": after["sequence_count"],
            "function_count": after["function_count"],
            "alembic_heads": after["alembic_heads"],
            "structure_sha256": after["structure_sha256"],
        },
        "public_delta": delta,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Day 4 PostgreSQL least-privilege roles without persistent writes.")
    parser.add_argument("--local-config", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    migration_url = str(__import__("os").environ.get("MIGRATION_DATABASE_URL", "")).strip()
    if not migration_url:
        raise RuntimeError("缺少 MIGRATION_DATABASE_URL。")
    runtime_url, security_url = _read_urls(args.local_config)
    result = run_guard(migration_url, runtime_url, security_url, args.baseline)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"status={result['status']}")
    print(f"evidence={args.evidence.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
