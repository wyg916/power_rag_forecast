from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.repositories.base import dumps_json, postgres_engine  # noqa: E402


SEED_SOURCE = "dashboard_seed"
SEED_DATA_SOURCE = "seed_demo"


def _latest_forecast_run(conn) -> str | None:
    return conn.execute(
        text(
            """
            SELECT run_id
            FROM forecast_runs
            ORDER BY COALESCE(generated_at, updated_at, created_at) DESC, run_id DESC
            LIMIT 1
            """
        )
    ).scalar()


def seed_forecast_if_missing(conn) -> int:
    latest_run_id = _latest_forecast_run(conn)
    row_count = 0
    if latest_run_id:
        row_count = int(
            conn.execute(
                text("SELECT COUNT(*) FROM forecast_results WHERE run_id = :run_id"),
                {"run_id": latest_run_id},
            ).scalar()
            or 0
        )
    if row_count >= 24:
        return 0

    run_id = "dashboard_seed_24h"
    start = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    prices = [108, 126, 131, 132, 130, 98, 96, 78, 77, 75, 72, 70, 86, 85, 84, 117, 118, 119, 90, 92, 94, 97, 99, 100]
    loads = [51500, 58400, 61200, 62000, 62500, 53000, 52600, 51200, 50600, 50000, 49200, 48700, 50800, 50300, 49800, 58100, 57900, 57400, 48100, 48600, 49200, 50000, 50700, 51200]
    risk_probs = [0.18, 0.55, 0.62, 0.66, 0.58, 0.24, 0.2, 0.08, 0.07, 0.06, 0.05, 0.05, 0.12, 0.11, 0.1, 0.52, 0.57, 0.54, 0.13, 0.14, 0.16, 0.18, 0.2, 0.22]
    summary = {
        "rows": 24,
        "region": "浙江省",
        "forecast_start": start.isoformat(sep=" "),
        "forecast_end": (start + timedelta(hours=23)).isoformat(sep=" "),
        "max_price": max(prices),
        "min_price": min(prices),
        "avg_price": sum(prices) / len(prices),
        "peak_valley_spread": max(prices) - min(prices),
        "high_risk_hours": sum(1 for item in risk_probs if item >= 0.5),
        "data_source": SEED_DATA_SOURCE,
        "source": SEED_SOURCE,
        "is_demo": True,
    }
    conn.execute(
        text(
            """
            INSERT INTO forecast_runs (
                run_id, source_path, forecast_start, forecast_end, generated_at,
                row_count, status, summary_json, created_at, updated_at
            )
            SELECT :run_id, :source_path, :forecast_start, :forecast_end, CURRENT_TIMESTAMP,
                   24, 'ready', CAST(:summary_json AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (SELECT 1 FROM forecast_runs WHERE run_id = :run_id)
            """
        ),
        {
            "run_id": run_id,
            "source_path": SEED_SOURCE,
            "forecast_start": start,
            "forecast_end": start + timedelta(hours=23),
            "summary_json": dumps_json(summary),
        },
    )
    inserted = 0
    for index, price in enumerate(prices):
        dt = start + timedelta(hours=index)
        risk_level = "high" if risk_probs[index] >= 0.5 else ("medium" if risk_probs[index] >= 0.2 else "low")
        result = conn.execute(
            text(
                """
                INSERT INTO forecast_results (
                    run_id, forecast_datetime, predicted_price, corrected_predicted_price,
                    risk_level, spike_risk_prob, forecast_load, source_row, raw_json, created_at
                )
                SELECT :run_id, :forecast_datetime, :predicted_price, :corrected_predicted_price,
                       :risk_level, :spike_risk_prob, :forecast_load, :source_row,
                       CAST(:raw_json AS jsonb), CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM forecast_results
                    WHERE run_id = :run_id AND source_row = :source_row
                )
                """
            ),
            {
                "run_id": run_id,
                "forecast_datetime": dt,
                "predicted_price": price,
                "corrected_predicted_price": price,
                "risk_level": risk_level,
                "spike_risk_prob": risk_probs[index],
                "forecast_load": loads[index],
                "source_row": index + 1,
                "raw_json": dumps_json(
                    {
                        "source": SEED_SOURCE,
                        "data_source": SEED_DATA_SOURCE,
                        "is_demo": True,
                        "confidence_low": round(price * 0.92, 3),
                        "confidence_high": round(price * 1.08, 3),
                    }
                ),
            },
        )
        inserted += int(result.rowcount or 0)
    return inserted


def seed_model_metrics(conn) -> int:
    version = conn.execute(
        text(
            """
            SELECT model_version
            FROM model_versions
            ORDER BY is_active DESC NULLS LAST, COALESCE(updated_at, created_at) DESC NULLS LAST
            LIMIT 1
            """
        )
    ).scalar()
    if not version:
        version = "v3.2.1"
        conn.execute(
            text(
                """
                INSERT INTO model_versions (
                    model_version, model_name, model_type, artifact_path, status,
                    is_active, metrics_json, created_at, updated_at
                )
                SELECT :version, 'price_forecast_model', 'forecast', '', 'Active',
                       TRUE, CAST(:metrics_json AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (SELECT 1 FROM model_versions WHERE model_version = :version)
                """
            ),
            {
                "version": version,
                "metrics_json": dumps_json({"source": SEED_SOURCE, "data_source": SEED_DATA_SOURCE, "is_demo": True}),
            },
        )

    metric_payload = {
        "source": SEED_SOURCE,
        "data_source": SEED_DATA_SOURCE,
        "is_demo": True,
        "note": "Dashboard demo metric used only when active model metrics are absent.",
    }
    conn.execute(
        text(
            """
            UPDATE model_versions
            SET metrics_json = COALESCE(metrics_json, '{}'::jsonb) || CAST(:metrics_json AS jsonb),
                updated_at = CURRENT_TIMESTAMP
            WHERE model_version = :version
              AND COALESCE(metrics_json ->> 'source', '') <> :source
            """
        ),
        {"version": version, "source": SEED_SOURCE, "metrics_json": dumps_json(metric_payload)},
    )
    updated = conn.execute(
        text(
            """
            UPDATE model_metrics
            SET mae = COALESCE(mae, 2.184),
                rmse = COALESCE(rmse, 3.476),
                r2 = COALESCE(r2, 0.932),
                mape = COALESCE(mape, 0.021),
                peak_error = COALESCE(peak_error, 5.82),
                sample_count = COALESCE(sample_count, 24),
                metrics_json = CAST(:metrics_json AS jsonb)
            WHERE model_version = :version
              AND (mae IS NULL OR rmse IS NULL)
            """
        ),
        {"version": version, "metrics_json": dumps_json(metric_payload)},
    )
    if int(updated.rowcount or 0) > 0:
        return int(updated.rowcount or 0)
    has_metric = conn.execute(
        text(
            """
            SELECT 1
            FROM model_metrics
            WHERE model_version = :version
              AND mae IS NOT NULL
              AND rmse IS NOT NULL
            LIMIT 1
            """
        ),
        {"version": version},
    ).scalar()
    if has_metric:
        return 0
    result = conn.execute(
        text(
            """
            INSERT INTO model_metrics (
                model_version, metric_date, mae, rmse, r2, mape, peak_error,
                sample_count, metrics_json, created_at
            )
            SELECT CAST(:version AS varchar), CURRENT_DATE, 2.184, 3.476, 0.932, 0.021, 5.82,
                   24, CAST(:metrics_json AS jsonb), CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM model_metrics
                WHERE model_version = :version AND metric_date = CURRENT_DATE
            )
            """
        ),
        {"version": version, "metrics_json": dumps_json(metric_payload)},
    )
    return int(result.rowcount or 0)


def seed_report_review(conn) -> int:
    report_id = conn.execute(
        text(
            """
            SELECT report_id
            FROM report_runs
            ORDER BY COALESCE(generated_at, updated_at, created_at) DESC, report_id DESC
            LIMIT 1
            """
        )
    ).scalar()
    if not report_id:
        return 0
    result = conn.execute(
        text(
            """
            INSERT INTO report_reviews (
                report_id, action, reviewer, comment, metadata_json, created_at
            )
            SELECT CAST(:report_id AS varchar), CAST('pending' AS varchar), CAST('dashboard_seed' AS varchar),
                   CAST('Dashboard 演示待审记录，用于首页报告待审 KPI 闭环。' AS text),
                   CAST(:metadata_json AS jsonb), CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM report_reviews
                WHERE report_id = :report_id
                  AND metadata_json ->> 'source' = :source
            )
            """
        ),
        {
            "report_id": report_id,
            "source": SEED_SOURCE,
            "metadata_json": dumps_json({"source": SEED_SOURCE, "data_source": SEED_DATA_SOURCE, "is_demo": True}),
        },
    )
    return int(result.rowcount or 0)


def seed_renewable(conn) -> int:
    existing = int(
        conn.execute(
            text("SELECT COUNT(*) FROM raw_renewable WHERE raw_json ->> 'source' = :source"),
            {"source": SEED_SOURCE},
        ).scalar()
        or 0
    )
    if existing >= 24:
        return 0
    latest_run_id = _latest_forecast_run(conn)
    start = conn.execute(
        text("SELECT MIN(forecast_datetime) FROM forecast_results WHERE run_id = :run_id"),
        {"run_id": latest_run_id},
    ).scalar() if latest_run_id else None
    start = start or datetime.now().replace(minute=0, second=0, microsecond=0)
    inserted = 0
    for index in range(24):
        dt = start + timedelta(hours=index)
        solar = max(0.0, 180 + 420 * (1 - abs(12 - index) / 12)) if 6 <= index <= 18 else 0.0
        wind = 260 + ((index * 37) % 120)
        storage = 80 if index in {2, 3, 4, 15, 16, 17} else 0
        total = solar + wind + storage
        result = conn.execute(
            text(
                """
                INSERT INTO raw_renewable (
                    market, datetime, solar_mw, wind_mw, storage_mw,
                    renewable_total_mw, source_file, source_row, raw_json,
                    created_at, updated_at
                )
                SELECT '浙江省', :datetime, :solar_mw, :wind_mw, :storage_mw,
                       :renewable_total_mw, :source_file, :source_row,
                       CAST(:raw_json AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM raw_renewable
                    WHERE raw_json ->> 'source' = :source AND source_row = :source_row
                )
                """
            ),
            {
                "datetime": dt,
                "solar_mw": round(solar, 3),
                "wind_mw": round(wind, 3),
                "storage_mw": round(storage, 3),
                "renewable_total_mw": round(total, 3),
                "source_file": SEED_SOURCE,
                "source_row": index + 1,
                "source": SEED_SOURCE,
                "raw_json": dumps_json({"source": SEED_SOURCE, "data_source": SEED_DATA_SOURCE, "is_demo": True}),
            },
        )
        inserted += int(result.rowcount or 0)
    return inserted


def main() -> None:
    engine = postgres_engine()
    if engine is None:
        raise SystemExit("PostgreSQL DATABASE_URL 不可用，无法 seed dashboard demo data。")
    with engine.begin() as conn:
        result = {
            "forecast_results": seed_forecast_if_missing(conn),
            "model_metrics": seed_model_metrics(conn),
            "report_reviews": seed_report_review(conn),
            "raw_renewable": seed_renewable(conn),
        }
    print(result)


if __name__ == "__main__":
    main()
