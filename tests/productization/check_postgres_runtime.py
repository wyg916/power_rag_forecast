from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "tests" / "productization" / "output"
REPORT_JSON = OUTPUT_DIR / "postgres_runtime_report.json"
REPORT_MD = OUTPUT_DIR / "postgres_runtime_report.md"

CORE_TABLES = [
    "forecast_runs",
    "forecast_results",
    "model_versions",
    "model_metrics",
    "report_runs",
    "report_reviews",
    "task_runs",
    "task_logs",
    "ai_traces",
    "audit_logs",
    "kb_documents",
    "kb_chunks",
    "users",
    "roles",
    "raw_market",
    "raw_weather",
    "raw_load",
    "raw_renewable",
    "feature_importance",
]

CORE_INDEXES = [
    "idx_forecast_results_run_id",
    "idx_forecast_results_datetime",
    "idx_model_metrics_version",
    "idx_task_runs_status",
    "idx_task_runs_execution_mode",
    "idx_task_runs_cancel_requested",
    "idx_task_runs_celery_task_id",
    "idx_task_logs_task_id",
    "idx_ai_traces_session",
    "idx_report_runs_run_id",
    "idx_kb_chunks_doc_id",
    "idx_audit_logs_action",
    "idx_users_role_id",
    "idx_raw_market_datetime",
    "idx_raw_weather_datetime",
    "idx_raw_load_datetime",
    "idx_raw_renewable_datetime",
    "idx_feature_importance_rank",
]


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def _masked_connection(database_url: str) -> dict[str, Any]:
    url = make_url(database_url)
    return {
        "driver": url.drivername,
        "host": url.host or "",
        "port": url.port or 5432,
        "user": url.username or "",
        "db": url.database or "",
        "password": "******" if url.password else "",
    }


def _alembic_heads() -> list[str]:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    return sorted(script.get_heads())


def _run_alembic_upgrade() -> dict[str, Any]:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    started = time.perf_counter()
    command.upgrade(cfg, "head")
    return {"executed": True, "duration_seconds": round(time.perf_counter() - started, 3)}


def _query_runtime_state(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        table_rows = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                """
            )
        ).scalars().all()
        index_rows = conn.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = current_schema()
                """
            )
        ).scalars().all()
        version_rows = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    tables = sorted(str(item) for item in table_rows)
    indexes = sorted(str(item) for item in index_rows)
    versions = sorted(str(item) for item in version_rows)
    heads = _alembic_heads()
    return {
        "table_count": len(tables),
        "index_count": len(indexes),
        "tables": tables,
        "indexes": indexes,
        "alembic_versions": versions,
        "alembic_heads": heads,
        "core_tables": {table: table in tables for table in CORE_TABLES},
        "core_indexes": {index: index in indexes for index in CORE_INDEXES},
        "missing_core_tables": [table for table in CORE_TABLES if table not in tables],
        "missing_core_indexes": [index for index in CORE_INDEXES if index not in indexes],
        "alembic_at_head": set(versions) == set(heads),
    }


def build_report(run_upgrade: bool = True) -> dict[str, Any]:
    database_url = _database_url()
    if not database_url:
        return {
            "status": "skipped",
            "runtime_check_available": False,
            "reason": "DATABASE_URL is not set in the current process environment.",
        }
    report: dict[str, Any] = {
        "runtime_check_available": True,
        "connection": _masked_connection(database_url),
    }
    try:
        if run_upgrade:
            report["alembic_upgrade"] = _run_alembic_upgrade()
        else:
            report["alembic_upgrade"] = {"executed": False, "reason": "--no-upgrade was specified"}
        state = _query_runtime_state(database_url)
        report["runtime_state"] = state
        report["status"] = "pass" if not state["missing_core_tables"] and state["alembic_at_head"] else "fail"
        if state["missing_core_indexes"]:
            report["status"] = "pass_with_warnings" if report["status"] == "pass" else report["status"]
        return report
    except Exception as exc:
        secret = make_url(database_url).password or ""
        error_text = str(exc).replace(secret, "******") if secret else str(exc)
        report.update({"status": "fail", "error_type": type(exc).__name__, "error": error_text})
        return report


def write_json(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def write_markdown(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# PostgreSQL 运行态验收报告", "", f"- 状态：`{report.get('status')}`"]
    if report.get("status") == "skipped":
        lines.extend(["", f"- 跳过原因：{report.get('reason')}"])
    else:
        conn = report.get("connection") or {}
        lines.extend(
            [
                f"- 连接：host={conn.get('host')} port={conn.get('port')} user={conn.get('user')} db={conn.get('db')} password=******",
                f"- Alembic upgrade head：{'已执行' if report.get('alembic_upgrade', {}).get('executed') else '未执行'}",
            ]
        )
        state = report.get("runtime_state") or {}
        core_tables = state.get("core_tables") or {}
        core_indexes = state.get("core_indexes") or {}
        lines.extend(
            [
                f"- Alembic version at head：{state.get('alembic_at_head')}",
                f"- 表数量：{state.get('table_count')}",
                f"- 索引数量：{state.get('index_count')}",
                "",
                "## 核心表",
                md_table(["表名", "存在"], [[name, "是" if ok else "否"] for name, ok in core_tables.items()]),
                "",
                "## 核心索引",
                md_table(["索引名", "存在"], [[name, "是" if ok else "否"] for name, ok in core_indexes.items()]),
            ]
        )
        if report.get("error"):
            lines.extend(["", "## 错误", f"- {report.get('error_type')}: {report.get('error')}"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PostgreSQL runtime and Alembic checks.")
    parser.add_argument("--no-upgrade", action="store_true", help="Only inspect the database; do not run alembic upgrade head.")
    parser.add_argument("--json", default=str(REPORT_JSON))
    parser.add_argument("--markdown", default=str(REPORT_MD))
    args = parser.parse_args()
    report = build_report(run_upgrade=not args.no_upgrade)
    write_json(report, Path(args.json))
    write_markdown(report, Path(args.markdown))
    print(f"PostgreSQL runtime report written: {args.markdown}")
    print(f"JSON report written: {args.json}")
    print(json.dumps({key: report.get(key) for key in ["status", "runtime_check_available"]}, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"pass", "pass_with_warnings", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
