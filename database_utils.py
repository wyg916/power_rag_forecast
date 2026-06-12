from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from automation_common import get_run_context, now_text, write_json


LogFunc = Callable[[str], None] | None

CORE_DATASET_TABLES = {
    "da_price_raw.xlsx": "raw_da_price",
    "rt_price_raw.xlsx": "raw_rt_price",
    "actual_load_raw.xlsx": "raw_actual_load",
    "forecast_load_raw.xlsx": "raw_forecast_load_history",
    "forecast_load_selected.xlsx": "raw_forecast_load_selected",
    "weather_raw.xlsx": "raw_weather",
    "master_table.xlsx": "model_master_table",
}

DATA_DICTIONARY_SHEETS = {
    "fields": "meta_data_dictionary_fields",
    "coverage": "meta_data_dictionary_coverage",
    "sources": "meta_data_dictionary_sources",
}

PREDICTION_INPUT_EXPORTS = {
    "model_master_table": "master_table.xlsx",
    "raw_forecast_load_selected": "forecast_load_selected.xlsx",
}

RESULT_FILE_TABLES = {
    "模型候选对比表.xlsx": "result_model_candidate_comparison",
    "高峰模型对比表.xlsx": "result_peak_model_comparison",
    "尖峰分类器对比表.xlsx": "result_spike_classifier_comparison",
    "尖峰分类器阈值搜索表.xlsx": "result_spike_classifier_threshold_search",
    "按价格分位数误差统计.xlsx": "result_price_quantile_error_stats",
    "预测偏差诊断.xlsx": "result_prediction_bias_diagnostics",
    "01_数据质量检查.xlsx": "result_data_quality_check",
    "02_数值字段描述统计.xlsx": "result_numeric_describe",
    "03_数据泄漏检查报告.xlsx": "result_data_leakage_check",
    "04_特征工程后建模表.xlsx": "result_model_feature_table",
    "05_候选模型验证集结果.xlsx": "result_candidate_validation",
    "06_高峰专项模型验证结果.xlsx": "result_peak_validation",
    "07_尖峰分类器验证结果.xlsx": "result_spike_classifier_validation",
    "08_融合参数搜索结果.xlsx": "result_blend_search",
    "09_高峰增强验证摘要.xlsx": "result_peak_enhancement_summary",
    "10_模型评估结果.xlsx": "result_model_evaluation",
    "11_高峰尖刺专项评估.xlsx": "result_peak_spike_evaluation",
    "12_测试集预测结果.xlsx": "result_test_predictions",
    "13_特征重要性.xlsx": "result_feature_importance",
    "14_异常波动明细.xlsx": "result_anomaly_details",
    "15_按小时误差统计.xlsx": "result_hourly_error_stats",
    "16_滚动回测结果.xlsx": "result_backtest_metrics",
    "17_滚动回测预测明细.xlsx": "result_backtest_predictions",
    "18_未来24小时预测结果_正式版.xlsx": "result_forward_24h_formal",
    "18_未来24小时预测结果_演示版.xlsx": "result_forward_24h_demo",
    "18_未来24小时预测输入特征_正式版.xlsx": "result_forward_24h_formal_features",
    "19_业务统计摘要.xlsx": "result_business_summary",
}

TEXT_INDEX_PREFIX_LENGTHS = {
    "run_id": 64,
    "run_mode": 32,
    "generated_at": 32,
    "created_at": 32,
    "event_time": 32,
    "summary_signature": 64,
    "risk_level": 16,
    "load_area": 64,
    "forecast_area": 64,
    "stage_name": 64,
    "status": 16,
    "source_file_name": 128,
    "node_name": 128,
    "weather_point_name": 128,
}

NATURAL_PRIMARY_KEY_CANDIDATES = {
    "raw_da_price": [("datetime", "node_id"), ("datetime",)],
    "raw_rt_price": [("datetime", "node_id"), ("datetime",)],
    "raw_actual_load": [("datetime",)],
    "raw_forecast_load_history": [("forecast_evaluated_at", "datetime")],
    "raw_forecast_load_selected": [("datetime",)],
    "raw_weather": [("datetime",)],
    "model_master_table": [("datetime", "node_id"), ("datetime",)],
}

SURROGATE_PRIMARY_KEY_TABLES = {
    *DATA_DICTIONARY_SHEETS.values(),
    *RESULT_FILE_TABLES.values(),
    "ai_input_summary_runs",
    "ai_report_runs",
    "dispatch_manifest_runs",
    "pipeline_run_events",
    "result_table_import_registry",
}

GUI_SOURCE_LABELS = OrderedDict(
    [
        ("vw_latest_run_overview", "最新运行总览（视图）"),
        ("vw_latest_ai_report", "最新 AI 报告（视图）"),
        ("vw_latest_ai_input_summary", "最新 AI 输入摘要（视图）"),
        ("vw_latest_forward_24h_formal", "最新正式前瞻预测结果（视图）"),
        ("vw_latest_pipeline_events", "最新流程事件（视图）"),
        ("vw_run_catalog", "运行批次目录（视图）"),
        ("vw_latest_active_model", "当前上线模型（视图）"),
        ("vw_recent_model_errors", "近期模型误差（视图）"),
        ("vw_model_comparison", "模型对比结果（视图）"),
        ("ai_report_runs", "AI 报告历史表"),
        ("ai_input_summary_runs", "AI 输入摘要历史表"),
        ("dispatch_manifest_runs", "结果归档历史表"),
        ("pipeline_run_events", "流程事件历史表"),
        ("prediction_tracking", "逐小时预测追踪表"),
        ("model_registry", "模型版本注册表"),
        ("model_performance_daily", "模型日度性能表"),
        ("model_retrain_jobs", "模型重训任务表"),
        ("model_comparison_runs", "模型候选对比表"),
        ("monitoring_metrics", "监控指标历史表"),
        ("ai_report_review_runs", "AI 报告审批流表"),
        ("report_approval_runs", "报告审批记录表"),
        ("audit_logs", "审计日志表"),
        ("result_forward_24h_formal", "正式前瞻预测结果历史表"),
        ("result_model_evaluation", "模型评估结果历史表"),
        ("result_peak_spike_evaluation", "高峰尖刺专项评估历史表"),
        ("result_hourly_error_stats", "按小时误差统计历史表"),
        ("result_anomaly_details", "异常波动明细历史表"),
        ("result_backtest_metrics", "滚动回测指标历史表"),
        ("result_test_predictions", "测试集预测结果历史表"),
        ("model_master_table", "建模主表"),
        ("raw_da_price", "日前电价原始表"),
        ("raw_rt_price", "实时电价原始表"),
        ("raw_actual_load", "实际负荷原始表"),
        ("raw_forecast_load_selected", "筛选后负荷预测表"),
        ("raw_forecast_load_history", "历史负荷预测原始表"),
        ("raw_weather", "天气原始表"),
    ]
)

VIEW_DEFINITIONS = {
    "vw_latest_ai_report": {
        "requires": ["ai_report_runs"],
        "sql": """
CREATE OR REPLACE VIEW `vw_latest_ai_report` AS
SELECT r.*
FROM `ai_report_runs` r
JOIN (
    SELECT MAX(`id`) AS `id`
    FROM `ai_report_runs`
) latest ON r.`id` = latest.`id`
""".strip(),
    },
    "vw_latest_ai_input_summary": {
        "requires": ["ai_input_summary_runs"],
        "sql": """
CREATE OR REPLACE VIEW `vw_latest_ai_input_summary` AS
SELECT s.*
FROM `ai_input_summary_runs` s
JOIN (
    SELECT MAX(`id`) AS `id`
    FROM `ai_input_summary_runs`
) latest ON s.`id` = latest.`id`
""".strip(),
    },
    "vw_latest_forward_24h_formal": {
        "requires": ["result_forward_24h_formal"],
        "sql": """
CREATE OR REPLACE VIEW `vw_latest_forward_24h_formal` AS
SELECT f.*
FROM `result_forward_24h_formal` f
JOIN (
    SELECT `run_id`
    FROM `result_forward_24h_formal`
    ORDER BY `id` DESC
    LIMIT 1
) latest ON f.`run_id` = latest.`run_id`
ORDER BY f.`datetime`
""".strip(),
    },
    "vw_latest_pipeline_events": {
        "requires": ["pipeline_run_events"],
        "sql": """
CREATE OR REPLACE VIEW `vw_latest_pipeline_events` AS
SELECT p.*
FROM `pipeline_run_events` p
JOIN (
    SELECT `run_id`
    FROM `pipeline_run_events`
    ORDER BY `id` DESC
    LIMIT 1
) latest ON p.`run_id` = latest.`run_id`
ORDER BY p.`id`
""".strip(),
    },
    "vw_run_catalog": {
        "requires": [
            "ai_input_summary_runs",
            "ai_report_runs",
            "dispatch_manifest_runs",
            "pipeline_run_events",
        ],
        "sql": """
CREATE OR REPLACE VIEW `vw_run_catalog` AS
SELECT
    base.`run_id`,
    MAX(base.`run_started_at`) AS `run_started_at`,
    MAX(base.`run_mode`) AS `run_mode`,
    MAX(base.`last_event_time`) AS `last_event_time`,
    MAX(base.`ai_summary_created_at`) AS `ai_summary_created_at`,
    MAX(base.`ai_report_generated_at`) AS `ai_report_generated_at`,
    MAX(base.`output_folder`) AS `output_folder`
FROM (
    SELECT
        `run_id`,
        `run_started_at`,
        `run_mode`,
        NULL AS `last_event_time`,
        `created_at` AS `ai_summary_created_at`,
        NULL AS `ai_report_generated_at`,
        NULL AS `output_folder`
    FROM `ai_input_summary_runs`
    UNION ALL
    SELECT
        `run_id`,
        `run_started_at`,
        `run_mode`,
        NULL AS `last_event_time`,
        NULL AS `ai_summary_created_at`,
        `generated_at` AS `ai_report_generated_at`,
        NULL AS `output_folder`
    FROM `ai_report_runs`
    UNION ALL
    SELECT
        `run_id`,
        `run_started_at`,
        `run_mode`,
        NULL AS `last_event_time`,
        NULL AS `ai_summary_created_at`,
        NULL AS `ai_report_generated_at`,
        `output_folder` AS `output_folder`
    FROM `dispatch_manifest_runs`
    UNION ALL
    SELECT
        `run_id`,
        `run_started_at`,
        `run_mode`,
        `event_time` AS `last_event_time`,
        NULL AS `ai_summary_created_at`,
        NULL AS `ai_report_generated_at`,
        NULL AS `output_folder`
    FROM `pipeline_run_events`
) base
GROUP BY base.`run_id`
""".strip(),
    },
    "vw_latest_run_overview": {
        "requires": [
            "ai_input_summary_runs",
            "ai_report_runs",
            "dispatch_manifest_runs",
            "pipeline_run_events",
        ],
        "sql": """
CREATE OR REPLACE VIEW `vw_latest_run_overview` AS
SELECT
    latest_runs.`run_id`,
    latest_runs.`run_started_at`,
    latest_runs.`run_mode`,
    latest_runs.`last_event_time`,
    summary.`forecast_mode`,
    summary.`forecast_start`,
    summary.`forecast_end`,
    summary.`next_24h_avg_price`,
    summary.`next_24h_max_price`,
    summary.`next_24h_max_hour`,
    summary.`next_24h_min_price`,
    summary.`next_24h_min_hour`,
    summary.`peak_valley_spread`,
    summary.`final_model`,
    summary.`rmse`,
    summary.`mae`,
    summary.`anomaly_count`,
    summary.`anomaly_ratio_pct`,
    report.`generated_at` AS `report_generated_at`,
    report.`risk_level`,
    report.`generator_provider`,
    report.`generator_model`,
    report.`generator_mode`,
    report.`word_report_path`,
    dispatch.`output_folder`
FROM (
    SELECT
        `run_id`,
        `run_started_at`,
        `run_mode`,
        `last_event_time`
    FROM `vw_run_catalog`
    ORDER BY `run_id` DESC
    LIMIT 1
) latest_runs
LEFT JOIN (
    SELECT summary_rows.*
    FROM `ai_input_summary_runs` summary_rows
    JOIN (
        SELECT `run_id`, MAX(`id`) AS `id`
        FROM `ai_input_summary_runs`
        GROUP BY `run_id`
    ) latest_summary ON summary_rows.`id` = latest_summary.`id`
) summary ON summary.`run_id` = latest_runs.`run_id`
LEFT JOIN (
    SELECT report_rows.*
    FROM `ai_report_runs` report_rows
    JOIN (
        SELECT `run_id`, MAX(`id`) AS `id`
        FROM `ai_report_runs`
        GROUP BY `run_id`
    ) latest_report ON report_rows.`id` = latest_report.`id`
) report ON report.`run_id` = latest_runs.`run_id`
LEFT JOIN (
    SELECT dispatch_rows.*
    FROM `dispatch_manifest_runs` dispatch_rows
    JOIN (
        SELECT `run_id`, MAX(`id`) AS `id`
        FROM `dispatch_manifest_runs`
        GROUP BY `run_id`
    ) latest_dispatch ON dispatch_rows.`id` = latest_dispatch.`id`
) dispatch ON dispatch.`run_id` = latest_runs.`run_id`
""".strip(),
    },
}


@dataclass
class DatabaseConfig:
    enabled: bool
    connection_name: str
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str
    connect_timeout: int


def _log(log: LogFunc, message: str) -> None:
    if log:
        log(message)


def _read_excel_safe(path: Path, log: LogFunc = None, *, sheet_name: str | int = 0) -> pd.DataFrame | None:
    """Read an Excel file for database sync without breaking the whole pipeline."""

    try:
        if not path.exists():
            return None
        if path.stat().st_size <= 0:
            _log(log, f"WARNING: 跳过空 Excel 文件：{path.name}")
            return None
        df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    except Exception as exc:
        _log(log, f"WARNING: 跳过无法读取的 Excel 文件：{path.name}，原因：{exc}")
        return None
    if df.empty:
        _log(log, f"WARNING: 跳过无数据记录的 Excel 文件：{path.name}")
        return None
    return df


def get_database_config(config: dict[str, Any]) -> DatabaseConfig:
    db_cfg = config.get("database", {})
    return DatabaseConfig(
        enabled=bool(db_cfg.get("enabled", False)),
        connection_name=str(db_cfg.get("connection_name", "")),
        host=str(db_cfg.get("host", "localhost")),
        port=int(db_cfg.get("port", 3306)),
        user=str(db_cfg.get("user", "")),
        password=str(db_cfg.get("password", "")),
        database=str(db_cfg.get("database", "")),
        charset=str(db_cfg.get("charset", "utf8mb4")),
        connect_timeout=int(db_cfg.get("connect_timeout", 10)),
    )


def _server_url(db: DatabaseConfig) -> str:
    return (
        f"mysql+pymysql://{quote_plus(db.user)}:{quote_plus(db.password)}@"
        f"{db.host}:{db.port}/mysql?charset={db.charset}"
    )


def _database_url(db: DatabaseConfig) -> str:
    return (
        f"mysql+pymysql://{quote_plus(db.user)}:{quote_plus(db.password)}@"
        f"{db.host}:{db.port}/{quote_plus(db.database)}?charset={db.charset}"
    )


def _quote_identifier(name: str) -> str:
    return f"`{name.replace('`', '')}`"


def create_server_engine(config: dict[str, Any]) -> Engine:
    db = get_database_config(config)
    return create_engine(_server_url(db), pool_pre_ping=True, future=True)


def create_database_engine(config: dict[str, Any]) -> Engine:
    db = get_database_config(config)
    return create_engine(_database_url(db), pool_pre_ping=True, future=True)


def ensure_database_ready(config: dict[str, Any], log: LogFunc = None) -> None:
    db = get_database_config(config)
    if not db.enabled:
        return
    db_name = db.database.replace("`", "")
    server_engine = create_server_engine(config)
    with server_engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS {_quote_identifier(db_name)} "
                f"CHARACTER SET {db.charset} COLLATE {db.charset}_unicode_ci"
            )
        )
    _log(log, f"数据库已就绪：{db.connection_name} / {db.database}")


def test_database_connection(config: dict[str, Any]) -> tuple[bool, str]:
    try:
        db = get_database_config(config)
        if not db.enabled:
            return True, "数据库未启用：当前将使用本地文件模式运行。"
        if db.enabled and not str(db.password or "").strip():
            return False, "数据库连接失败：未配置 DB_PASSWORD。请在项目根目录 .env 或系统环境变量中设置数据库密码。"
        ensure_database_ready(config)
        engine = create_database_engine(config)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, f"数据库连接成功：{db.connection_name} / {db.database}"
    except Exception as exc:
        return False, f"数据库连接失败：{exc}"


def _split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for raw_line in sql_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        current.append(raw_line)
        if line.endswith(";"):
            statement = "\n".join(current).rstrip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            current = []
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail.rstrip(";").strip())
    return statements


def apply_database_migrations(
    config: dict[str, Any],
    migrations_dir: Path | None = None,
    log: LogFunc = None,
) -> list[str]:
    """执行 migrations 目录中的幂等 SQL 脚本，并记录执行版本。"""

    db = get_database_config(config)
    if not db.enabled:
        _log(log, "数据库未启用，跳过 migrations。")
        return []

    ensure_database_ready(config, log)
    migration_path = migrations_dir or Path(__file__).resolve().parent / "migrations"
    if not migration_path.exists():
        raise FileNotFoundError(f"未找到 migrations 目录：{migration_path}")

    engine = create_database_engine(config)
    applied: list[str] = []
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(32) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        existing = {
            str(row[0])
            for row in conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
        }
        for sql_file in sorted(migration_path.glob("*.sql")):
            version = sql_file.stem.split("_", 1)[0]
            if version in existing:
                _log(log, f"跳过已执行迁移：{sql_file.name}")
                continue
            sql_text = sql_file.read_text(encoding="utf-8")
            for statement in _split_sql_statements(sql_text):
                conn.execute(text(statement))
            conn.execute(
                text(
                    """
                    INSERT INTO schema_migrations (version, name, applied_at)
                    VALUES (:version, :name, CURRENT_TIMESTAMP)
                    """
                ),
                {"version": version, "name": sql_file.name},
            )
            applied.append(sql_file.name)
            _log(log, f"已执行数据库迁移：{sql_file.name}")
    return applied


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def normalize_dataframe_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            output[column] = pd.to_datetime(output[column], errors="coerce").dt.tz_localize(None)
        elif output[column].dtype == "object":
            output[column] = output[column].map(_normalize_value)
    return output


def _sql_type_for_series(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "DATETIME NULL"
    if pd.api.types.is_bool_dtype(series):
        return "TINYINT NULL"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT NULL"
    if pd.api.types.is_float_dtype(series):
        return "DOUBLE NULL"
    return "TEXT NULL"


def _ensure_append_columns(engine: Engine, table_name: str, df: pd.DataFrame, log: LogFunc = None) -> None:
    if df.empty:
        return
    with engine.begin() as conn:
        exists = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalar()
        if not exists:
            return
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                      AND table_name = :table_name
                    """
                ),
                {"table_name": table_name},
            )
        }
        missing = [column for column in df.columns if str(column) not in existing]
        for column in missing:
            sql_type = _sql_type_for_series(df[column])
            conn.execute(
                text(
                    f"ALTER TABLE {_quote_identifier(table_name)} "
                    f"ADD COLUMN {_quote_identifier(str(column))} {sql_type}"
                )
            )
        if missing:
            _log(log, f"数据表 {table_name} 已自动补齐新增字段：{'、'.join(map(str, missing))}")


def write_dataframe(
    config: dict[str, Any],
    table_name: str,
    df: pd.DataFrame,
    if_exists: str = "replace",
    log: LogFunc = None,
) -> None:
    if not get_database_config(config).enabled:
        _log(log, f"数据库未启用，跳过写入数据表：{table_name}")
        return
    ensure_database_ready(config, log)
    engine = create_database_engine(config)
    normalized = normalize_dataframe_for_sql(df)
    if if_exists == "append":
        _ensure_append_columns(engine, table_name, normalized, log=log)
    normalized.to_sql(
        table_name,
        engine,
        if_exists=if_exists,
        index=False,
        chunksize=2000,
        method="multi",
    )
    _log(log, f"已写入数据表：{table_name}，记录数：{len(normalized)}，写入方式：{if_exists}")


def append_records(config: dict[str, Any], table_name: str, rows: list[dict[str, Any]], log: LogFunc = None) -> None:
    if not rows:
        return
    write_dataframe(config, table_name, pd.DataFrame(rows), if_exists="append", log=log)


def read_dataframe_from_db(config: dict[str, Any], table_name: str) -> pd.DataFrame:
    if not get_database_config(config).enabled:
        raise RuntimeError(f"数据库未启用，无法读取数据表：{table_name}")
    ensure_database_ready(config)
    engine = create_database_engine(config)
    query = text(f"SELECT * FROM {_quote_identifier(table_name)}")
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def write_excel_snapshot(path: Path, df: pd.DataFrame) -> None:
    output = df.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            output[column] = pd.to_datetime(output[column], errors="coerce").dt.tz_localize(None)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        output.to_excel(writer, index=False)


def sync_core_datasets_to_database(data_dir: Path, config: dict[str, Any], log: LogFunc = None) -> None:
    if not get_database_config(config).enabled:
        _log(log, "数据库未启用，跳过核心数据集落库。")
        return
    ensure_database_ready(config, log)
    for filename, table_name in CORE_DATASET_TABLES.items():
        path = data_dir / filename
        if not path.exists():
            continue
        df = _read_excel_safe(path, log=log)
        if df is None:
            continue
        write_dataframe(config, table_name, df, if_exists="replace", log=log)

    dictionary_path = data_dir / "data_dictionary.xlsx"
    if dictionary_path.exists():
        for sheet_name, table_name in DATA_DICTIONARY_SHEETS.items():
            df = _read_excel_safe(dictionary_path, log=log, sheet_name=sheet_name)
            if df is None:
                continue
            write_dataframe(config, table_name, df, if_exists="replace", log=log)
    ensure_database_structures(config, log=log)


def export_prediction_inputs_from_database(data_dir: Path, config: dict[str, Any], log: LogFunc = None) -> None:
    if not get_database_config(config).enabled:
        missing = [filename for filename in PREDICTION_INPUT_EXPORTS.values() if not (data_dir / filename).exists()]
        if missing:
            raise FileNotFoundError(
                "数据库未启用，且本地预测输入文件缺失："
                + "、".join(missing)
                + "。请先配置数据库或运行数据刷新生成本地文件。"
            )
        _log(log, "数据库未启用，复用本地预测输入文件。")
        return
    ensure_database_ready(config, log)
    for table_name, filename in PREDICTION_INPUT_EXPORTS.items():
        df = read_dataframe_from_db(config, table_name)
        write_excel_snapshot(data_dir / filename, df)
        _log(log, f"已从数据库导出预测输入文件：{filename}，记录数：{len(df)}")


def sync_result_tables_to_database(
    result_table_dir: Path,
    config: dict[str, Any],
    run_context: dict[str, str] | None = None,
    log: LogFunc = None,
    filenames: set[str] | list[str] | tuple[str, ...] | None = None,
) -> None:
    if not get_database_config(config).enabled:
        _log(log, "数据库未启用，跳过预测结果表同步。")
        return
    ensure_database_ready(config, log)
    context = run_context or get_run_context()
    registry_rows: list[dict[str, Any]] = []
    allowed_files = set(filenames) if filenames else None

    for filename, table_name in RESULT_FILE_TABLES.items():
        if allowed_files is not None and filename not in allowed_files:
            continue
        path = result_table_dir / filename
        if not path.exists():
            continue
        df = _read_excel_safe(path, log=log)
        if df is None:
            continue
        output = df.copy()
        output.insert(0, "run_id", context["run_id"])
        output.insert(1, "run_mode", context["run_mode"])
        output.insert(2, "run_started_at", context["run_started_at"])
        output.insert(3, "source_file_name", filename)
        output.insert(4, "db_imported_at", now_text())
        write_dataframe(config, table_name, output, if_exists="append", log=log)
        registry_rows.append(
            {
                "run_id": context["run_id"],
                "run_mode": context["run_mode"],
                "run_started_at": context["run_started_at"],
                "source_file_name": filename,
                "target_table_name": table_name,
                "row_count": len(df),
                "imported_at": now_text(),
            }
        )

    append_records(config, "result_table_import_registry", registry_rows, log=log)
    ensure_database_structures(config, log=log)


def save_ai_input_summary(
    config: dict[str, Any],
    summary: dict[str, Any],
    run_context: dict[str, str] | None = None,
    log: LogFunc = None,
) -> None:
    if not get_database_config(config).enabled:
        _log(log, "数据库未启用，跳过 AI 输入摘要落库。")
        return
    ensure_database_ready(config, log)
    context = run_context or get_run_context()
    forecast = summary.get("forecast_summary", {})
    model = summary.get("model_summary", {})
    anomaly = summary.get("anomaly_summary", {})

    row = {
        "run_id": context["run_id"],
        "run_mode": context["run_mode"],
        "run_started_at": context["run_started_at"],
        "generated_at": summary.get("generated_at"),
        "summary_signature": summary.get("summary_signature"),
        "forecast_mode": summary.get("forecast_mode"),
        "forecast_start": forecast.get("forecast_start"),
        "forecast_end": forecast.get("forecast_end"),
        "next_24h_avg_price": forecast.get("next_24h_avg_price"),
        "next_24h_max_price": forecast.get("next_24h_max_price"),
        "next_24h_max_hour": forecast.get("next_24h_max_hour"),
        "next_24h_min_price": forecast.get("next_24h_min_price"),
        "next_24h_min_hour": forecast.get("next_24h_min_hour"),
        "peak_valley_spread": forecast.get("peak_valley_spread"),
        "final_model": model.get("final_model"),
        "rmse": model.get("rmse"),
        "mae": model.get("mae"),
        "anomaly_count": anomaly.get("anomaly_count"),
        "anomaly_ratio_pct": anomaly.get("anomaly_ratio_pct"),
        "summary_json": json.dumps(summary, ensure_ascii=False),
        "created_at": now_text(),
    }
    append_records(config, "ai_input_summary_runs", [row], log=log)
    ensure_database_structures(config, log=log)


def save_ai_report(
    config: dict[str, Any],
    report: dict[str, Any],
    word_report_path: Path,
    run_context: dict[str, str] | None = None,
    log: LogFunc = None,
) -> None:
    if not get_database_config(config).enabled:
        _log(log, "数据库未启用，跳过 AI 报告落库。")
        return
    ensure_database_ready(config, log)
    context = run_context or get_run_context()
    generator = report.get("generator", {})
    full_report_text = "\n\n".join(
        [
            str(report.get("executive_summary", "")),
            str(report.get("market_overview", "")),
            str(report.get("next_24h_trend", "")),
            str(report.get("peak_risk", "")),
            "\n".join(report.get("operation_advice", [])),
            str(report.get("management_summary", "")),
            str(report.get("alert_message", "")),
            str(report.get("limitations", "")),
        ]
    ).strip()

    row = {
        "run_id": context["run_id"],
        "run_mode": context["run_mode"],
        "run_started_at": context["run_started_at"],
        "generated_at": now_text(),
        "summary_signature": report.get("summary_signature"),
        "risk_level": report.get("risk_level"),
        "key_hours_json": json.dumps(report.get("key_hours", []), ensure_ascii=False),
        "executive_summary": report.get("executive_summary"),
        "market_overview": report.get("market_overview"),
        "next_24h_trend": report.get("next_24h_trend"),
        "peak_risk": report.get("peak_risk"),
        "operation_advice_json": json.dumps(report.get("operation_advice", []), ensure_ascii=False),
        "management_summary": report.get("management_summary"),
        "alert_message": report.get("alert_message"),
        "limitations": report.get("limitations"),
        "generator_provider": generator.get("provider"),
        "generator_model": generator.get("model"),
        "generator_mode": generator.get("mode"),
        "word_report_path": str(word_report_path),
        "word_report_size_bytes": word_report_path.stat().st_size if word_report_path.exists() else 0,
        "full_report_text": full_report_text,
        "report_json": json.dumps(report, ensure_ascii=False),
    }
    append_records(config, "ai_report_runs", [row], log=log)
    ensure_database_structures(config, log=log)


def save_dispatch_manifest(
    config: dict[str, Any],
    manifest: dict[str, Any],
    output_folder: Path,
    run_context: dict[str, str] | None = None,
    log: LogFunc = None,
) -> None:
    if not get_database_config(config).enabled:
        _log(log, "数据库未启用，跳过归档 manifest 落库。")
        return
    ensure_database_ready(config, log)
    context = run_context or get_run_context()
    row = {
        "run_id": context["run_id"],
        "run_mode": context["run_mode"],
        "run_started_at": context["run_started_at"],
        "output_folder": str(output_folder),
        "manifest_json": json.dumps(manifest, ensure_ascii=False),
        "created_at": now_text(),
    }
    append_records(config, "dispatch_manifest_runs", [row], log=log)
    write_json(output_folder / "数据库归档副本.json", manifest)
    ensure_database_structures(config, log=log)


def save_pipeline_event(
    config: dict[str, Any],
    stage_name: str,
    status: str,
    message: str,
    run_context: dict[str, str] | None = None,
) -> None:
    if not get_database_config(config).enabled:
        return
    context = run_context or get_run_context()
    row = {
        "run_id": context["run_id"],
        "run_mode": context["run_mode"],
        "run_started_at": context["run_started_at"],
        "stage_name": stage_name,
        "status": status,
        "message": message,
        "event_time": now_text(),
    }
    append_records(config, "pipeline_run_events", [row], log=None)


def list_table_and_view_names(config: dict[str, Any]) -> dict[str, set[str]]:
    ensure_database_ready(config)
    engine = create_database_engine(config)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                      AND table_type = 'BASE TABLE'
                    """
                )
            ).fetchall()
        }
        views = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.views
                    WHERE table_schema = DATABASE()
                    """
                )
            ).fetchall()
        }
    return {"tables": tables, "views": views}


def _table_exists(conn, table_name: str) -> bool:
    query = text(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
        """
    )
    return int(conn.execute(query, {"table_name": table_name}).scalar() or 0) > 0


def _view_exists(conn, view_name: str) -> bool:
    query = text(
        """
        SELECT COUNT(*)
        FROM information_schema.views
        WHERE table_schema = DATABASE()
          AND table_name = :view_name
        """
    )
    return int(conn.execute(query, {"view_name": view_name}).scalar() or 0) > 0


def _column_metadata(conn, table_name: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable, column_key
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
            ORDER BY ordinal_position
            """
        ),
        {"table_name": table_name},
    ).fetchall()
    return {
        str(row[0]): {
            "data_type": str(row[1]).lower(),
            "is_nullable": str(row[2]).upper() == "YES",
            "column_key": str(row[3]),
        }
        for row in rows
    }


def _has_primary_key(conn, table_name: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.table_constraints
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND constraint_type = 'PRIMARY KEY'
            """
        ),
        {"table_name": table_name},
    ).scalar()
    return int(row or 0) > 0


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND index_name = :index_name
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    ).scalar()
    return int(row or 0) > 0


def _quote_column_fragment(column_name: str, metadata: dict[str, dict[str, Any]]) -> str:
    base = _quote_identifier(column_name)
    data_type = metadata[column_name]["data_type"]
    if data_type in {"text", "tinytext", "mediumtext", "longtext"}:
        length = TEXT_INDEX_PREFIX_LENGTHS.get(column_name, 64)
        return f"{base}({length})"
    return base


def _is_candidate_key_available(conn, table_name: str, columns: tuple[str, ...], metadata: dict[str, dict[str, Any]]) -> bool:
    if not all(column in metadata for column in columns):
        return False

    not_null_filters = " OR ".join(f"{_quote_identifier(column)} IS NULL" for column in columns)
    null_count = conn.execute(
        text(f"SELECT COUNT(*) FROM {_quote_identifier(table_name)} WHERE {not_null_filters}")
    ).scalar()
    if int(null_count or 0) > 0:
        return False

    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    duplicate_query = text(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT {column_sql}, COUNT(*) AS cnt
            FROM {_quote_identifier(table_name)}
            GROUP BY {column_sql}
            HAVING COUNT(*) > 1
        ) dup
        """
    )
    duplicate_count = conn.execute(duplicate_query).scalar()
    return int(duplicate_count or 0) == 0


def _ensure_primary_key(conn, table_name: str, log: LogFunc = None) -> None:
    if not _table_exists(conn, table_name):
        return
    if _has_primary_key(conn, table_name):
        return

    metadata = _column_metadata(conn, table_name)
    candidates = NATURAL_PRIMARY_KEY_CANDIDATES.get(table_name, [])
    for columns in candidates:
        if _is_candidate_key_available(conn, table_name, columns, metadata):
            column_sql = ", ".join(_quote_identifier(column) for column in columns)
            conn.execute(text(f"ALTER TABLE {_quote_identifier(table_name)} ADD PRIMARY KEY ({column_sql})"))
            _log(log, f"已为数据表添加主键：{table_name} -> ({', '.join(columns)})")
            return

    if table_name in SURROGATE_PRIMARY_KEY_TABLES:
        if "id" not in metadata:
            conn.execute(
                text(
                    f"ALTER TABLE {_quote_identifier(table_name)} "
                    "ADD COLUMN `id` BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST"
                )
            )
            _log(log, f"已为数据表添加自增主键：{table_name}.id")
            return
        if not _has_primary_key(conn, table_name):
            conn.execute(
                text(
                    f"ALTER TABLE {_quote_identifier(table_name)} "
                    "MODIFY COLUMN `id` BIGINT NOT NULL AUTO_INCREMENT, ADD PRIMARY KEY (`id`)"
                )
            )
            _log(log, f"已为数据表补齐主键约束：{table_name}.id")
            return

    _log(log, f"跳过主键创建：{table_name}，未找到可安全落地的主键方案")


def _build_index_specs(table_name: str, metadata: dict[str, dict[str, Any]]) -> list[tuple[str, list[str]]]:
    columns = set(metadata)
    specs: list[tuple[str, list[str]]] = []

    def _add(name: str, cols: list[str]) -> None:
        if all(col in columns for col in cols):
            specs.append((name, cols))

    if "run_id" in columns:
        _add("idx_run_id", ["run_id"])
    if "datetime" in columns:
        _add("idx_datetime", ["datetime"])
    if "generated_at" in columns:
        _add("idx_generated_at", ["generated_at"])
    if "created_at" in columns:
        _add("idx_created_at", ["created_at"])
    if "event_time" in columns:
        _add("idx_event_time", ["event_time"])
    if "summary_signature" in columns:
        _add("idx_summary_signature", ["summary_signature"])
    if "risk_level" in columns:
        _add("idx_risk_level", ["risk_level"])
    if {"run_id", "datetime"}.issubset(columns):
        _add("idx_run_id_datetime", ["run_id", "datetime"])
    if {"node_id", "datetime"}.issubset(columns):
        _add("idx_node_id_datetime", ["node_id", "datetime"])
    if {"load_area", "datetime"}.issubset(columns):
        _add("idx_load_area_datetime", ["load_area", "datetime"])
    if {"forecast_area", "datetime"}.issubset(columns):
        _add("idx_forecast_area_datetime", ["forecast_area", "datetime"])
    if {"forecast_evaluated_at", "datetime"}.issubset(columns):
        _add("idx_forecast_eval_datetime", ["forecast_evaluated_at", "datetime"])
    if "forecast_anchor_time" in columns:
        _add("idx_forecast_anchor_time", ["forecast_anchor_time"])
    if {"stage_name", "status"}.issubset(columns):
        _add("idx_stage_status", ["stage_name", "status"])
    if {"source_file_name", "run_id"}.issubset(columns):
        _add("idx_source_file_run", ["source_file_name", "run_id"])
    if {"weather_point_name", "datetime"}.issubset(columns):
        _add("idx_weather_point_datetime", ["weather_point_name", "datetime"])

    return specs


def _ensure_indexes(conn, table_name: str, log: LogFunc = None) -> None:
    if not _table_exists(conn, table_name):
        return
    metadata = _column_metadata(conn, table_name)
    for index_name, columns in _build_index_specs(table_name, metadata):
        if _index_exists(conn, table_name, index_name):
            continue
        column_sql = ", ".join(_quote_column_fragment(column, metadata) for column in columns)
        conn.execute(
            text(
                f"ALTER TABLE {_quote_identifier(table_name)} "
                f"ADD INDEX {_quote_identifier(index_name)} ({column_sql})"
            )
        )
        _log(log, f"已为数据表添加索引：{table_name}.{index_name}")


def _ensure_views(conn, log: LogFunc = None) -> None:
    existing_tables = {
        row[0]
        for row in conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_type = 'BASE TABLE'
                """
            )
        ).fetchall()
    }
    for view_name, definition in VIEW_DEFINITIONS.items():
        required_tables = set(definition["requires"])
        if not required_tables.issubset(existing_tables):
            _log(log, f"跳过视图创建：{view_name}，缺少依赖表")
            continue
        conn.execute(text(definition["sql"]))
        if _view_exists(conn, view_name):
            _log(log, f"已创建或更新视图：{view_name}")


def ensure_database_structures(config: dict[str, Any], log: LogFunc = None) -> None:
    ensure_database_ready(config, log)
    engine = create_database_engine(config)
    relations = list_table_and_view_names(config)
    table_names = sorted(relations["tables"])
    with engine.begin() as conn:
        for table_name in table_names:
            _ensure_primary_key(conn, table_name, log=log)
            _ensure_indexes(conn, table_name, log=log)
        _ensure_views(conn, log=log)


def list_database_browse_sources(config: dict[str, Any]) -> list[dict[str, str]]:
    relations = list_table_and_view_names(config)
    all_names = relations["views"] | relations["tables"]
    ordered_sources: list[dict[str, str]] = []
    used_names: set[str] = set()

    for name, label in GUI_SOURCE_LABELS.items():
        if name in all_names:
            ordered_sources.append({"name": name, "label": label})
            used_names.add(name)

    for name in sorted(all_names - used_names):
        ordered_sources.append({"name": name, "label": name})

    return ordered_sources


def _relation_columns(conn, relation_name: str) -> list[str]:
    rows = conn.execute(text(f"SHOW COLUMNS FROM {_quote_identifier(relation_name)}")).fetchall()
    return [str(row[0]) for row in rows]


def _pick_order_column(columns: list[str]) -> str | None:
    for name in ["id", "event_time", "generated_at", "created_at", "db_imported_at", "datetime"]:
        if name in columns:
            return name
    return None


def preview_relation(
    config: dict[str, Any],
    relation_name: str,
    limit: int = 200,
    run_id: str | None = None,
) -> pd.DataFrame:
    ensure_database_ready(config)
    engine = create_database_engine(config)
    safe_limit = max(1, min(int(limit), 1000))
    with engine.connect() as conn:
        columns = _relation_columns(conn, relation_name)
        where_clauses: list[str] = []
        params: dict[str, Any] = {"limit": safe_limit}
        if run_id and "run_id" in columns and not relation_name.startswith("vw_latest_"):
            where_clauses.append("`run_id` = :run_id")
            params["run_id"] = run_id
        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        order_sql = ""
        if relation_name == "vw_latest_forward_24h_formal" and "datetime" in columns:
            order_sql = " ORDER BY `datetime` ASC"
        elif relation_name == "vw_latest_pipeline_events" and "id" in columns:
            order_sql = " ORDER BY `id` ASC"
        else:
            order_column = _pick_order_column(columns)
            order_sql = f" ORDER BY {_quote_identifier(order_column)} DESC" if order_column else ""
        query = text(
            f"SELECT * FROM {_quote_identifier(relation_name)}{where_sql}{order_sql} LIMIT :limit"
        )
        return pd.read_sql(query, conn, params=params)


def fetch_recent_run_catalog(config: dict[str, Any], limit: int = 50) -> pd.DataFrame:
    ensure_database_ready(config)
    engine = create_database_engine(config)
    safe_limit = max(1, min(int(limit), 500))
    with engine.connect() as conn:
        if _view_exists(conn, "vw_run_catalog"):
            query = text(
                """
                SELECT *
                FROM `vw_run_catalog`
                ORDER BY `run_id` DESC
                LIMIT :limit
                """
            )
            return pd.read_sql(query, conn, params={"limit": safe_limit})

        fallback_query = text(
            """
            SELECT
                base.run_id,
                MAX(base.run_started_at) AS run_started_at,
                MAX(base.run_mode) AS run_mode,
                MAX(base.last_event_time) AS last_event_time
            FROM (
                SELECT run_id, run_started_at, run_mode, NULL AS last_event_time FROM ai_input_summary_runs
                UNION ALL
                SELECT run_id, run_started_at, run_mode, generated_at AS last_event_time FROM ai_report_runs
                UNION ALL
                SELECT run_id, run_started_at, run_mode, event_time AS last_event_time FROM pipeline_run_events
            ) base
            GROUP BY base.run_id
            ORDER BY base.run_id DESC
            LIMIT :limit
            """
        )
        return pd.read_sql(fallback_query, conn, params={"limit": safe_limit})


def fetch_ai_report_record(config: dict[str, Any], run_id: str | None = None) -> dict[str, Any] | None:
    ensure_database_ready(config)
    engine = create_database_engine(config)
    with engine.connect() as conn:
        columns = _relation_columns(conn, "ai_report_runs")
        order_column = "id" if "id" in columns else "generated_at"
        if run_id:
            query = text(
                f"""
                SELECT *
                FROM `ai_report_runs`
                WHERE `run_id` = :run_id
                ORDER BY {_quote_identifier(order_column)} DESC
                LIMIT 1
                """
            )
            row = conn.execute(query, {"run_id": run_id}).mappings().fetchone()
        else:
            query = text(
                f"""
                SELECT *
                FROM `ai_report_runs`
                ORDER BY {_quote_identifier(order_column)} DESC
                LIMIT 1
                """
            )
            row = conn.execute(query).mappings().fetchone()
    return dict(row) if row else None


def fetch_database_overview(config: dict[str, Any]) -> dict[str, Any]:
    ensure_database_ready(config)
    relations = list_table_and_view_names(config)
    latest_run_id = ""
    latest_report_mode = ""
    latest_report_time = ""
    latest_risk_level = ""
    engine = create_database_engine(config)

    with engine.connect() as conn:
        run_catalog = fetch_recent_run_catalog(config, limit=1)
        if not run_catalog.empty:
            latest_run_id = str(run_catalog.iloc[0].get("run_id", "") or "")

        report_row = fetch_ai_report_record(config, run_id=latest_run_id or None)
        if not report_row:
            report_row = fetch_ai_report_record(config, run_id=None)
        if report_row:
            latest_report_mode = str(report_row.get("generator_mode", "") or "")
            latest_report_time = str(report_row.get("generated_at", "") or "")
            latest_risk_level = str(report_row.get("risk_level", "") or "")

        result = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND index_name <> 'PRIMARY'
                """
            )
        ).scalar()
        index_count = int(result or 0)

    db_cfg = get_database_config(config)
    return {
        "database_name": db_cfg.database,
        "table_count": len(relations["tables"]),
        "view_count": len(relations["views"]),
        "index_count": index_count,
        "latest_run_id": latest_run_id,
        "latest_report_mode": latest_report_mode,
        "latest_report_time": latest_report_time,
        "latest_risk_level": latest_risk_level,
    }
