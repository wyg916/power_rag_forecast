from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .base import jsonable, loads_json, mapping_dict, mapping_list, postgres_engine


def _merge_metrics(version: dict[str, Any], latest_metric: dict[str, Any] | None) -> dict[str, Any]:
    metrics_json = loads_json(version.get("metrics_json"), default={})
    row = dict(metrics_json) if isinstance(metrics_json, dict) else {}
    row.update({key: value for key, value in version.items() if key != "metrics_json"})
    if latest_metric:
        row.update(
            {
                "test_mae": latest_metric.get("mae"),
                "test_rmse": latest_metric.get("rmse"),
                "test_r2": latest_metric.get("r2"),
                "mape": latest_metric.get("mape"),
                "peak_rmse": latest_metric.get("peak_error"),
                "sample_count": latest_metric.get("sample_count"),
                "metric_date": latest_metric.get("metric_date"),
            }
        )
    row["is_active"] = bool(row.get("is_active"))
    return jsonable(row)


def model_status_from_postgres() -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            version_rows = conn.execute(
                text(
                    """
                    SELECT model_version, model_name, model_type, artifact_path, status,
                           is_active, metrics_json, created_at, updated_at
                    FROM model_versions
                    ORDER BY is_active DESC NULLS LAST,
                             COALESCE(created_at, updated_at) DESC NULLS LAST,
                             model_version DESC
                    LIMIT 50
                    """
                )
            ).mappings().all()
            metric_rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT ON (model_version)
                           model_version, metric_date, mae, rmse, r2, mape,
                           peak_error, sample_count, metrics_json, created_at
                    FROM model_metrics
                    ORDER BY model_version, metric_date DESC NULLS LAST, created_at DESC
                    """
                )
            ).mappings().all()
            error_rows = conn.execute(
                text(
                    """
                    SELECT model_version, metric_date AS forecast_date, sample_count,
                           mae, peak_error AS max_abs_error
                    FROM model_metrics
                    ORDER BY metric_date DESC NULLS LAST, created_at DESC
                    LIMIT 60
                    """
                )
            ).mappings().all()
    except Exception:
        return None

    versions_raw = mapping_list(version_rows)
    if not versions_raw:
        return None
    latest_metric_by_version = {row["model_version"]: row for row in mapping_list(metric_rows)}
    versions = [
        _merge_metrics(version, latest_metric_by_version.get(version.get("model_version")))
        for version in versions_raw
    ]
    active = next((item for item in versions if item.get("is_active")), versions[0] if versions else {})
    return {
        "active": jsonable(active),
        "versions": jsonable(versions),
        "errors": mapping_list(error_rows),
        "source": "postgresql",
    }


def model_errors_from_postgres() -> dict[str, Any] | None:
    payload = model_status_from_postgres()
    if payload is None:
        return None
    return {"records": payload.get("errors") or []}
