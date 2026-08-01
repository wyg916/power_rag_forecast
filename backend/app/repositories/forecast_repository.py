from __future__ import annotations

from statistics import mean
from typing import Any

from sqlalchemy import text

from .base import jsonable, loads_json, mapping_dict, mapping_list, postgres_engine


def _compute_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    prices = [
        float(item["predicted_price"])
        for item in records
        if item.get("predicted_price") is not None
    ]
    if not records:
        return {}
    high_risk = [
        item
        for item in records
        if str(item.get("risk_level") or "").lower() in {"high", "danger"}
        or float(item.get("spike_risk_prob") or 0) >= 0.5
    ]
    max_row = max(records, key=lambda item: float(item.get("predicted_price") or -10**12))
    min_row = min(records, key=lambda item: float(item.get("predicted_price") or 10**12))
    return jsonable(
        {
            "rows": len(records),
            "forecast_start": records[0].get("datetime"),
            "forecast_end": records[-1].get("datetime"),
            "max_price": max(prices) if prices else None,
            "min_price": min(prices) if prices else None,
            "avg_price": mean(prices) if prices else None,
            "peak_valley_spread": max(prices) - min(prices) if prices else None,
            "max_hour": max_row.get("datetime"),
            "min_hour": min_row.get("datetime"),
            "high_risk_hours": len(high_risk),
            "focus_hours": [str(item.get("datetime"))[:16] for item in high_risk[:6]],
        }
    )


_RUN_SELECT = """
    run_id, status, domain, target_name,
    forecast_start_at, forecast_end_at, input_start_at, input_end_at,
    model_id, model_version, artifact_id, artifact_hash,
    feature_version, schema_hash, input_hash, result_hash,
    source_type, created_at, started_at, finished_at,
    error_code, error_message, retry_of_run_id, environment_hash, record_count,
    input_batch_id, source_metadata_json, freshness_status, development_mode
"""


def get_forecast_run(run_id: str, *, engine=None) -> dict[str, Any] | None:
    engine = engine or postgres_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            run = conn.execute(
                text(
                    f"SELECT {_RUN_SELECT} FROM forecast_runs WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            ).mappings().first()
    except Exception:
        return None
    return mapping_dict(run) if run else None


def list_forecast_runs(
    *,
    status: str | None = None,
    limit: int = 50,
    engine=None,
) -> list[dict[str, Any]]:
    engine = engine or postgres_engine()
    if engine is None:
        return []
    safe_limit = max(1, min(int(limit), 200))
    where = "WHERE status = :status" if status else ""
    params: dict[str, Any] = {"limit": safe_limit}
    if status:
        params["status"] = status
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT {_RUN_SELECT}
                    FROM forecast_runs
                    {where}
                    ORDER BY COALESCE(finished_at, started_at, created_at) DESC, run_id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
    except Exception:
        return []
    return mapping_list(rows)


def load_forecast_results(run_id: str, *, engine=None) -> list[dict[str, Any]]:
    engine = engine or postgres_engine()
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT run_id, forecast_time, predicted_price,
                           model_version, feature_version, generated_at,
                           base_prediction, peak_prediction, classifier_prediction,
                           spike_risk_prob, p90_prediction, blend_weight,
                           adjustment, component_outputs, source_type, source_row,
                           input_batch_id, forecast_load, risk_level
                    FROM forecast_results
                    WHERE run_id = :run_id
                    ORDER BY forecast_time, source_row, id
                    """
                ),
                {"run_id": run_id},
            ).mappings().all()
    except Exception:
        return []
    records = []
    for item in mapping_list(rows):
        item["datetime"] = item.pop("forecast_time", None)
        item["spike_probability"] = item.get("spike_risk_prob")
        records.append(item)
    return records


def latest_successful_run(*, engine=None) -> dict[str, Any] | None:
    engine = engine or postgres_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            run = conn.execute(
                text(
                    f"""
                    SELECT {_RUN_SELECT}
                    FROM forecast_runs
                    WHERE status = 'success' AND record_count = 24
                      AND (SELECT COUNT(*) FROM forecast_results r WHERE r.run_id = forecast_runs.run_id) = 24
                    ORDER BY finished_at DESC NULLS LAST, created_at DESC, run_id DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
    except Exception:
        return None
    return mapping_dict(run) if run else None


def load_latest_forecast_from_postgres() -> dict[str, Any] | None:
    engine = postgres_engine()
    run_dict = latest_successful_run(engine=engine)
    if not run_dict:
        return None
    records = load_forecast_results(str(run_dict["run_id"]), engine=engine)
    if len(records) != 24:
        return None
    summary = _compute_summary(records)
    return {
        "run_id": run_dict.get("run_id"),
        "source": "postgresql.forecast_runs",
        "available": True,
        "generated_at": run_dict.get("finished_at") or run_dict.get("created_at"),
        "price_column": "predicted_price",
        "risk_probability_column": "spike_risk_prob",
        "summary": jsonable(summary),
        "records": records,
        "source_type": "postgresql",
        "model_version": run_dict.get("model_version"),
        "feature_version": run_dict.get("feature_version"),
        "artifact_id": run_dict.get("artifact_id"),
        "result_hash": run_dict.get("result_hash"),
    }
