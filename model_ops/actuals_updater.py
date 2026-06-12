from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import text

from database_utils import apply_database_migrations, create_database_engine, get_database_config


@dataclass
class ActualsUpdateResult:
    scanned: int
    matched: int
    updated: int
    skipped_reason: str = ""


def calculate_error_values(predicted_price: float, actual_price: float) -> dict[str, float]:
    abs_error = abs(float(actual_price) - float(predicted_price))
    denominator = abs(float(actual_price)) if abs(float(actual_price)) > 1e-9 else 1e-9
    pct_error = abs_error / denominator * 100.0
    return {"abs_error": abs_error, "pct_error": pct_error}


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
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
    )


def _relation_columns(conn, table_name: str) -> list[str]:
    rows = conn.execute(text(f"SHOW COLUMNS FROM `{table_name}`")).fetchall()
    return [str(row[0]) for row in rows]


def _pick_price_column(columns: list[str]) -> str | None:
    preferred = ["da_price", "total_lmp_da", "lmp", "price", "value"]
    lower_map = {c.lower(): c for c in columns}
    for name in preferred:
        if name in lower_map:
            return lower_map[name]
    for col in columns:
        low = col.lower()
        if "price" in low or "lmp" in low:
            return col
    return None


def update_actuals_and_errors(config: dict[str, Any], limit: int = 5000, log=None) -> ActualsUpdateResult:
    """从 raw_da_price 回填 prediction_tracking 的真实值和误差。"""

    if not get_database_config(config).enabled:
        if log:
            log("数据库未启用，跳过真实值回填。")
        return ActualsUpdateResult(0, 0, 0, "database_disabled")

    apply_database_migrations(config, log=log)
    engine = create_database_engine(config)
    with engine.begin() as conn:
        if not _table_exists(conn, "prediction_tracking"):
            return ActualsUpdateResult(0, 0, 0, "prediction_tracking_missing")
        if not _table_exists(conn, "raw_da_price"):
            return ActualsUpdateResult(0, 0, 0, "raw_da_price_missing")

        raw_columns = _relation_columns(conn, "raw_da_price")
        if "datetime" not in raw_columns:
            return ActualsUpdateResult(0, 0, 0, "raw_da_price_datetime_missing")
        price_col = _pick_price_column(raw_columns)
        if not price_col:
            return ActualsUpdateResult(0, 0, 0, "raw_da_price_price_column_missing")

        pending = pd.read_sql(
            text(
                """
                SELECT id, forecast_datetime, predicted_price, model_version
                FROM prediction_tracking
                WHERE actual_price IS NULL
                ORDER BY forecast_datetime ASC
                LIMIT :limit
                """
            ),
            conn,
            params={"limit": max(1, int(limit))},
        )
        if pending.empty:
            return ActualsUpdateResult(0, 0, 0, "no_pending_records")

        min_dt = pending["forecast_datetime"].min()
        max_dt = pending["forecast_datetime"].max()
        actuals = pd.read_sql(
            text(
                f"""
                SELECT `datetime`, `{price_col}` AS actual_price
                FROM raw_da_price
                WHERE `datetime` BETWEEN :min_dt AND :max_dt
                """
            ),
            conn,
            params={"min_dt": min_dt, "max_dt": max_dt},
        )
        if actuals.empty:
            return ActualsUpdateResult(len(pending), 0, 0, "no_actuals_matched")

        pending["forecast_datetime"] = pd.to_datetime(pending["forecast_datetime"]).dt.floor("h")
        actuals["forecast_datetime"] = pd.to_datetime(actuals["datetime"]).dt.floor("h")
        actuals = actuals.dropna(subset=["forecast_datetime", "actual_price"]).drop_duplicates("forecast_datetime")
        merged = pending.merge(actuals[["forecast_datetime", "actual_price"]], on="forecast_datetime", how="inner")

        updated = 0
        for row in merged.itertuples(index=False):
            errors = calculate_error_values(row.predicted_price, row.actual_price)
            conn.execute(
                text(
                    """
                    UPDATE prediction_tracking
                    SET actual_price = :actual_price,
                        abs_error = :abs_error,
                        pct_error = :pct_error,
                        filled_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {
                    "id": int(row.id),
                    "actual_price": float(row.actual_price),
                    "abs_error": errors["abs_error"],
                    "pct_error": errors["pct_error"],
                },
            )
            updated += 1

        refresh_model_performance_daily(conn)
        if log:
            log(f"真实值回填完成：扫描 {len(pending)} 条，匹配 {len(merged)} 条，更新 {updated} 条。")
        return ActualsUpdateResult(len(pending), len(merged), updated)


def refresh_model_performance_daily(conn) -> int:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS model_performance_daily (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                model_version VARCHAR(64) NOT NULL,
                metric_date DATE NOT NULL,
                sample_count INT NOT NULL,
                mae DECIMAL(12,6) NULL,
                rmse DECIMAL(12,6) NULL,
                mape DECIMAL(12,6) NULL,
                peak_rmse DECIMAL(12,6) NULL,
                spike_rmse DECIMAL(12,6) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_model_perf_daily (model_version, metric_date)
            )
            """
        )
    )
    result = conn.execute(
        text(
            """
            INSERT INTO model_performance_daily (
                model_version, metric_date, sample_count, mae, rmse, mape, peak_rmse, spike_rmse
            )
            SELECT
                model_version,
                DATE(forecast_datetime) AS metric_date,
                COUNT(*) AS sample_count,
                AVG(abs_error) AS mae,
                SQRT(AVG(POW(actual_price - predicted_price, 2))) AS rmse,
                AVG(pct_error) AS mape,
                SQRT(AVG(CASE WHEN is_peak_hour = 1 THEN POW(actual_price - predicted_price, 2) ELSE NULL END)) AS peak_rmse,
                SQRT(AVG(CASE WHEN is_spike_risk = 1 THEN POW(actual_price - predicted_price, 2) ELSE NULL END)) AS spike_rmse
            FROM prediction_tracking
            WHERE actual_price IS NOT NULL
            GROUP BY model_version, DATE(forecast_datetime)
            ON DUPLICATE KEY UPDATE
                sample_count = VALUES(sample_count),
                mae = VALUES(mae),
                rmse = VALUES(rmse),
                mape = VALUES(mape),
                peak_rmse = VALUES(peak_rmse),
                spike_rmse = VALUES(spike_rmse)
            """
        )
    )
    return int(result.rowcount or 0)
