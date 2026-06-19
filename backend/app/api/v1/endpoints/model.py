from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from ....core.config import PROJECT_ROOT
from ....core.security import CurrentUser, require_permission
from ....data_access import artifact_inventory, model_status, query_dataframe, records
from ....observability import log_suppressed_exception


router = APIRouter()
P2_OUTPUT_DIR = PROJECT_ROOT / "output" / "p2"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text_excerpt(path: Path, *, max_chars: int = 4000) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars]


def _p2_file(name: str) -> Path:
    return P2_OUTPUT_DIR / name


def _metric_rows(metrics: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for item in metrics:
        overall = item.get("overall") or {}
        peak = item.get("peak") or {}
        spike = item.get("spike") or {}
        extreme = item.get("extreme_weather") or {}
        rows.append(
            {
                "split": item.get("split"),
                "model": item.get("model"),
                "time_range": item.get("time_range") or {},
                "overall": {
                    "mae": overall.get("mae"),
                    "rmse": overall.get("rmse"),
                    "mape": overall.get("mape"),
                    "r2": overall.get("r2"),
                    "sample_count": overall.get("sample_count"),
                },
                "peak": {
                    "mae": peak.get("peak_hour_mae"),
                    "rmse": peak.get("peak_hour_rmse"),
                    "bias": peak.get("peak_hour_bias"),
                    "sample_count": peak.get("peak_hour_sample_count"),
                },
                "spike": {
                    "threshold": spike.get("spike_threshold"),
                    "precision": spike.get("precision"),
                    "recall": spike.get("recall"),
                    "f1": spike.get("f1"),
                    "false_positive_count": spike.get("false_positive_count"),
                    "false_negative_count": spike.get("false_negative_count"),
                },
                "extreme_weather": {
                    "definition": extreme.get("definition"),
                    "mae": extreme.get("extreme_weather_mae"),
                    "rmse": extreme.get("extreme_weather_rmse"),
                    "sample_count": extreme.get("sample_count"),
                },
                "hourly_worst": sorted(
                    item.get("hourly") or [],
                    key=lambda row: float(row.get("mae") or 0),
                    reverse=True,
                )[:5],
            }
        )
    return rows


def p2_backtest_summary_payload() -> dict:
    metrics_path = _p2_file("metrics.json")
    report_path = _p2_file("backtest_report.md")
    metrics = _read_json(metrics_path)
    metric_items = metrics.get("metrics") or []
    rows = _metric_rows(metric_items)
    test_rows = [row for row in rows if row.get("split") == "test"]
    reference = next((row for row in test_rows if row.get("model") == "persistence_24h"), test_rows[0] if test_rows else None)
    return {
        "available": bool(metrics),
        "created_at": metrics.get("created_at"),
        "acceptable_for_backtest": metrics.get("acceptable_for_backtest"),
        "spike_threshold": metrics.get("spike_threshold"),
        "baseline_methods": metrics.get("baseline_methods") or {},
        "metrics": rows,
        "reference_baseline": reference,
        "baseline_comparisons": metrics.get("baseline_comparisons") or [],
        "schema_checks": metrics.get("schema_checks") or {},
        "leakage_check": metrics.get("leakage_check") or {},
        "warnings": metrics.get("warnings") or [],
        "report_excerpt": _read_text_excerpt(report_path),
        "output_paths": metrics.get("output_paths") or {},
        "paths": {
            "metrics": str(metrics_path),
            "backtest_report": str(report_path),
        },
    }


def p2_feature_schema_payload() -> dict:
    schema_path = _p2_file("feature_schema.json")
    schema = _read_json(schema_path)
    features = schema.get("features") or []
    source_counts: dict[str, int] = {}
    leakage_counts: dict[str, int] = {}
    for feature in features:
        source = str(feature.get("source_table") or "unknown")
        risk = str(feature.get("leakage_risk") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
        leakage_counts[risk] = leakage_counts.get(risk, 0) + 1
    return {
        "available": bool(schema),
        "schema_version": schema.get("schema_version"),
        "created_at": schema.get("created_at"),
        "time_field": schema.get("time_field"),
        "target": schema.get("target") or {},
        "feature_count": schema.get("feature_count") or len(features),
        "segment_columns": schema.get("segment_columns") or [],
        "source_table_counts": source_counts,
        "leakage_risk_counts": leakage_counts,
        "features": features,
        "feature_sample": features[:20],
        "schema_gate": {
            "ok": bool(schema and features),
            "message": "feature_schema.json 已生成" if schema and features else "feature_schema.json 不存在或为空",
        },
        "path": str(schema_path),
    }


def p2_leakage_check_payload() -> dict:
    result_path = _p2_file("leakage_check_result.json")
    report_path = _p2_file("leakage_check_report.md")
    result = _read_json(result_path)
    high = int(result.get("high_risk_count") or 0)
    medium = int(result.get("medium_risk_count") or 0)
    acceptable = bool(result.get("acceptable_for_backtest")) and high == 0
    return {
        "available": bool(result),
        "created_at": result.get("created_at"),
        "acceptable_for_backtest": result.get("acceptable_for_backtest"),
        "gate_status": "passed" if acceptable else "blocked",
        "high_risk_count": high,
        "medium_risk_count": medium,
        "issue_count": int(result.get("issue_count") or 0),
        "issues": result.get("issues") or [],
        "checks": result.get("checks") or {},
        "split_windows": result.get("split_windows") or {},
        "report_excerpt": _read_text_excerpt(report_path),
        "paths": {
            "leakage_check_result": str(result_path),
            "leakage_check_report": str(report_path),
        },
    }


@router.get("/api/models/active")
def models_active(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    return model_status().get("active", {})


@router.get("/api/models/metrics")
def models_metrics(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    payload = model_status()
    payload["artifacts"] = artifact_inventory()
    return payload


@router.get("/api/models/errors")
def models_errors(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    try:
        from ....repositories.model_repository import model_errors_from_postgres

        payload = model_errors_from_postgres()
        if payload is not None:
            return payload
    except Exception as exc:
        log_suppressed_exception("api.models_errors.postgres", exc)

    df = query_dataframe(
        """
        SELECT model_version, DATE(forecast_datetime) AS forecast_date,
               COUNT(*) AS sample_count, AVG(abs_error) AS mae, MAX(abs_error) AS max_abs_error
        FROM prediction_tracking
        WHERE actual_price IS NOT NULL
        GROUP BY model_version, DATE(forecast_datetime)
        ORDER BY forecast_date DESC
        LIMIT 60
        """
    )
    return {"records": records(df)}


@router.get("/api/models/retrain-suggestion")
def models_retrain_suggestion(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    try:
        from model_ops.auto_retrain_policy import check_model_degradation
        from ....config import project_config

        decision = check_model_degradation(project_config())
        return decision.__dict__
    except Exception as exc:
        return {"should_retrain": False, "retrain_reason": f"重训判断暂不可用：{exc}", "degradation_metrics": {}, "recommended_strategy": {}}


@router.get("/api/models/backtest/summary")
@router.get("/api/model/backtest/summary")
def models_backtest_summary(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    return p2_backtest_summary_payload()


@router.get("/api/models/feature-schema")
@router.get("/api/model/feature-schema")
def models_feature_schema(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    return p2_feature_schema_payload()


@router.get("/api/models/leakage-check")
@router.get("/api/model/leakage-check")
def models_leakage_check(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    return p2_leakage_check_payload()
