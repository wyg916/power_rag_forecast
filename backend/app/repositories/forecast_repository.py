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


def load_latest_forecast_from_postgres() -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            run = conn.execute(
                text(
                    """
                    SELECT run_id, source_path, forecast_start, forecast_end, generated_at,
                           row_count, status, summary_json, created_at, updated_at
                    FROM forecast_runs
                    ORDER BY COALESCE(generated_at, updated_at, created_at) DESC, run_id DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if run is None:
                return None
            rows = conn.execute(
                text(
                    """
                    SELECT run_id, forecast_datetime, predicted_price, corrected_predicted_price,
                           risk_level, spike_risk_prob, forecast_load, source_row, raw_json
                    FROM forecast_results
                    WHERE run_id = :run_id
                    ORDER BY forecast_datetime NULLS LAST, source_row NULLS LAST, id
                    """
                ),
                {"run_id": run["run_id"]},
            ).mappings().all()
    except Exception:
        return None

    records: list[dict[str, Any]] = []
    for item in mapping_list(rows):
        raw = loads_json(item.get("raw_json"), default={})
        record = raw if isinstance(raw, dict) else {}
        record.update(
            {
                "run_id": item.get("run_id"),
                "datetime": item.get("forecast_datetime"),
                "predicted_price": item.get("predicted_price"),
                "corrected_predicted_price": item.get("corrected_predicted_price"),
                "risk_level": item.get("risk_level"),
                "spike_risk_prob": item.get("spike_risk_prob"),
                "forecast_load": item.get("forecast_load"),
                "source_row": item.get("source_row"),
            }
        )
        records.append(jsonable(record))

    run_dict = mapping_dict(run)
    summary = loads_json(run_dict.get("summary_json"), default={})
    if not isinstance(summary, dict) or not summary:
        summary = _compute_summary(records)
    return {
        "run_id": run_dict.get("run_id"),
        "source": run_dict.get("source_path") or "postgresql.forecast_runs",
        "available": bool(records) or bool(run_dict),
        "generated_at": run_dict.get("generated_at") or run_dict.get("updated_at") or run_dict.get("created_at"),
        "price_column": "predicted_price",
        "risk_probability_column": "spike_risk_prob",
        "summary": jsonable(summary),
        "records": records,
        "source_type": "postgresql",
    }
