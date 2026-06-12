from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation_common import load_config
from database_utils import get_database_config


DEFAULT_REPORT = ROOT / "output" / "postgres_migration_report.csv"

BASELINE_TABLES = [
    "forecast_runs",
    "forecast_results",
    "model_versions",
    "model_metrics",
    "task_runs",
    "task_logs",
    "ai_traces",
    "report_runs",
    "report_reviews",
    "pv_tariff_rules",
    "pv_policy_files",
    "pv_station_tariff_check",
    "market_power_price_rules",
    "southern_grid_tax_rules",
    "pv_tariff_period_rules",
]

LEGACY_OPTIONAL_TABLES = [
    "model_registry",
    "prediction_tracking",
    "model_performance_daily",
    "model_retrain_jobs",
    "model_comparison_runs",
    "model_error_memory",
    "model_strategy_memory",
    "analysis_runs",
    "strategy_advice",
    "ai_chat_sessions",
    "ai_chat_messages",
    "anomaly_explanations",
    "ai_conversation_state",
    "ai_answer_feedback",
    "ai_chat_feedback",
]

JSON_COLUMNS = {
    "summary_json",
    "raw_json",
    "metrics_json",
    "command_json",
    "payload_json",
    "tools_json",
    "evidence_json",
    "guard_result_json",
    "trace_json",
    "metadata_json",
    "content_json",
    "evidence",
}


def _mysql_url_from_legacy_config() -> str:
    cfg = load_config()
    db = get_database_config(cfg)
    if not db.enabled:
        raise RuntimeError("MySQL 源库未启用，请设置 MYSQL_DATABASE_URL 或 DB_* 兼容配置。")
    if not db.password:
        raise RuntimeError("MySQL 源库缺少密码，请设置 MYSQL_DATABASE_URL 或 DB_PASSWORD。")
    return (
        f"mysql+pymysql://{quote_plus(db.user)}:{quote_plus(db.password)}@"
        f"{db.host}:{db.port}/{quote_plus(db.database)}?charset={db.charset}"
    )


def mysql_url(args: argparse.Namespace) -> str:
    return args.mysql_url or os.environ.get("MYSQL_DATABASE_URL") or _mysql_url_from_legacy_config()


def postgres_url(args: argparse.Namespace) -> str:
    url = args.postgres_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("PostgreSQL 目标库未配置，请设置 DATABASE_URL 或传入 --postgres-url。")
    return url


def create_db_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def table_exists(engine: Engine, table_name: str) -> bool:
    return inspect(engine).has_table(table_name)


def count_rows(engine: Engine, table_name: str) -> int:
    if not table_exists(engine, table_name):
        return 0
    with engine.connect() as conn:
        return int(conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar() or 0)


def mysql_count_rows(engine: Engine, table_name: str) -> int:
    if not table_exists(engine, table_name):
        return 0
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar() or 0)


def normalize_json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        try:
            return json.loads(text_value)
        except Exception:
            return text_value
    return value


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in output.columns:
        lower = str(column).lower()
        if lower in JSON_COLUMNS or lower.endswith("_json"):
            output[column] = output[column].map(normalize_json_value)
        elif any(token in lower for token in ["datetime", "created_at", "updated_at", "started_at", "ended_at", "generated_at", "activated_at", "metric_date", "publish_date", "start_date", "end_date", "grid_date"]):
            converted = pd.to_datetime(output[column], errors="coerce")
            output[column] = converted.where(converted.notna(), None)
    return output.where(pd.notna(output), None)


def reset_identity_sequence(engine: Engine, table_name: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                SELECT setval(pg_get_serial_sequence(:table_name, 'id'), COALESCE((SELECT MAX(id) FROM "{table_name}"), 1), true)
                """.replace("{table_name}", table_name)
            ),
            {"table_name": table_name},
        )


def reflected_table(engine: Engine, table_name: str) -> Table:
    metadata = MetaData()
    return Table(table_name, metadata, autoload_with=engine)


def insert_chunk(target: Engine, table_name: str, df: pd.DataFrame) -> int:
    table = reflected_table(target, table_name)
    target_columns = set(table.c.keys())
    columns = [column for column in df.columns if column in target_columns]
    if not columns:
        return 0
    records = df[columns].to_dict(orient="records")
    if not records:
        return 0
    with target.begin() as conn:
        conn.execute(table.insert(), records)
    return len(records)


def sample_hash(engine: Engine, table_name: str, dialect: str, limit: int = 5) -> str:
    if not table_exists(engine, table_name):
        return ""
    quote_left, quote_right = ("`", "`") if dialect == "mysql" else ('"', '"')
    with engine.connect() as conn:
        query = f"SELECT * FROM {quote_left}{table_name}{quote_right} LIMIT {limit}"
        rows = [dict(row) for row in conn.execute(text(query)).mappings().fetchall()]
    normalized = json.dumps(rows, ensure_ascii=False, default=str, sort_keys=True)
    return str(abs(hash(normalized)))


def migrate_table(
    source: Engine,
    target: Engine,
    table_name: str,
    chunksize: int,
    truncate_target: bool,
    dry_run: bool,
) -> dict[str, Any]:
    started = datetime.now()
    row = {
        "table_name": table_name,
        "source_rows": 0,
        "target_before": 0,
        "migrated_rows": 0,
        "target_after": 0,
        "sample_source_hash": "",
        "sample_target_hash": "",
        "status": "skipped",
        "message": "",
        "started_at": started.isoformat(sep=" ", timespec="seconds"),
        "ended_at": "",
    }
    try:
        if not table_exists(source, table_name):
            row["message"] = "source table missing"
            return row
        if not table_exists(target, table_name):
            row["message"] = "target table missing; run alembic upgrade head first"
            row["status"] = "failed"
            return row

        source_rows = mysql_count_rows(source, table_name)
        target_before = count_rows(target, table_name)
        row["source_rows"] = source_rows
        row["target_before"] = target_before
        row["sample_source_hash"] = sample_hash(source, table_name, "mysql")
        if dry_run:
            row["status"] = "dry_run"
            row["message"] = "not migrated"
            return row

        if truncate_target:
            with target.begin() as conn:
                conn.execute(text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE'))
            target_before = 0
            row["target_before"] = 0

        migrated = 0
        query = f"SELECT * FROM `{table_name}`"
        for chunk in pd.read_sql(text(query), source, chunksize=chunksize):
            normalized = normalize_frame(chunk)
            migrated += insert_chunk(target, table_name, normalized)

        target_columns = [column.get("name") for column in inspect(target).get_columns(table_name)]
        if migrated and "id" in target_columns:
            try:
                reset_identity_sequence(target, table_name)
            except Exception:
                pass

        row["migrated_rows"] = migrated
        row["target_after"] = count_rows(target, table_name)
        row["sample_target_hash"] = sample_hash(target, table_name, "postgres")
        row["status"] = "success" if migrated == source_rows else "warning"
        row["message"] = "row count matched" if migrated == source_rows else "migrated row count differs from source row count"
        return row
    except Exception as exc:
        row["status"] = "failed"
        row["message"] = str(exc)
        return row
    finally:
        row["ended_at"] = datetime.now().isoformat(sep=" ", timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate selected MySQL tables to PostgreSQL and write a CSV validation report.")
    parser.add_argument("--mysql-url", default="", help="Source MySQL SQLAlchemy URL. Defaults to MYSQL_DATABASE_URL or legacy DB_* config.")
    parser.add_argument("--postgres-url", default="", help="Target PostgreSQL SQLAlchemy URL. Defaults to DATABASE_URL.")
    parser.add_argument("--tables", default="", help="Comma-separated table names to migrate. Defaults to baseline PostgreSQL core tables.")
    parser.add_argument("--include-legacy", action="store_true", help="Also inspect legacy MySQL tables that are not part of the current PostgreSQL baseline.")
    parser.add_argument("--chunksize", type=int, default=1000)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--truncate-target", action="store_true", help="Truncate each target table before copying. Use only after backup/confirmation.")
    parser.add_argument("--dry-run", action="store_true", help="Only inspect source/target counts without writing.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = create_db_engine(mysql_url(args))
    target = create_db_engine(postgres_url(args))
    if args.tables:
        tables = [item.strip() for item in args.tables.split(",") if item.strip()]
    else:
        tables = list(BASELINE_TABLES)
        if args.include_legacy:
            tables.extend(LEGACY_OPTIONAL_TABLES)
    report_rows = [
        migrate_table(source, target, table_name, args.chunksize, args.truncate_target, args.dry_run)
        for table_name in tables
    ]
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()) if report_rows else ["table_name", "status"])
        writer.writeheader()
        writer.writerows(report_rows)
    print(f"migration report written: {report_path}")


if __name__ == "__main__":
    main()
