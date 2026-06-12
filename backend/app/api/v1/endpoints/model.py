from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ....core.security import CurrentUser, require_permission
from ....data_access import artifact_inventory, model_status, query_dataframe, records
from ....observability import log_suppressed_exception


router = APIRouter()


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
