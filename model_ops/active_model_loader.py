from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from automation_common import get_pipeline_paths, load_config
from database_utils import apply_database_migrations, create_database_engine, get_database_config
from prediction_engine.legacy_engine import load_engine_module
from prediction_engine.model_trainer import load_model_artifacts


REQUIRED_ARTIFACT_FILES = [
    "base_model.joblib",
    "peak_model.joblib",
    "spike_classifier.joblib",
    "feature_cols.json",
    "metrics.json",
    "training_config.json",
]


class ActiveModelUnavailable(RuntimeError):
    """Raised when fast forecast cannot safely load an active model."""


@dataclass
class ActiveModelBundle:
    record: dict[str, Any]
    artifact_dir: Path
    artifacts: dict[str, Any]
    feature_cols: list[str]
    metrics: dict[str, Any]
    training_config: dict[str, Any]
    feature_version: str | None
    model_version: str


def get_active_model_record(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    db = get_database_config(config)
    if db.enabled:
        apply_database_migrations(config)
        engine = create_database_engine(config)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM model_registry
                    WHERE is_active = 1
                    ORDER BY activated_at DESC, created_at DESC
                    LIMIT 1
                    """
                )
            ).mappings().fetchone()
        if row:
            return dict(row)

    model_cfg = config.get("model_learning", {}) or {}
    configured_path = str(model_cfg.get("active_artifact_path") or "").strip()
    if configured_path:
        paths = get_pipeline_paths(config)
        artifact_path = Path(configured_path)
        if not artifact_path.is_absolute():
            artifact_path = paths.root_dir / artifact_path
        return {
            "model_version": artifact_path.name,
            "model_role": "forecast",
            "status": "local_configured_active",
            "is_active": 1,
            "artifact_path": str(artifact_path),
        }

    raise ActiveModelUnavailable("当前没有可用 Active 模型，请先执行一次完整训练并设为 Active。")


def validate_artifact_files(artifact_dir: str | Path) -> list[str]:
    path = Path(artifact_dir)
    return [name for name in REQUIRED_ARTIFACT_FILES if not (path / name).exists()]


def load_feature_cols(artifact_dir: str | Path) -> list[str]:
    loaded = load_model_artifacts(artifact_dir)
    return list(loaded["feature_cols"])


def load_model_metrics(artifact_dir: str | Path) -> dict[str, Any]:
    loaded = load_model_artifacts(artifact_dir)
    return dict(loaded["metrics"])


def load_active_model_artifacts(config: dict[str, Any] | None = None) -> ActiveModelBundle:
    config = config or load_config()
    record = get_active_model_record(config)
    artifact_dir = Path(str(record.get("artifact_path") or ""))
    if not artifact_dir.is_absolute():
        artifact_dir = get_pipeline_paths(config).root_dir / artifact_dir

    missing = validate_artifact_files(artifact_dir)
    if missing:
        raise ActiveModelUnavailable(
            "Active 模型 artifact 不完整，缺失文件："
            + "、".join(missing)
            + "。请重新训练或重新设定 Active 模型。"
        )

    loaded = load_model_artifacts(artifact_dir)
    thresholds = loaded.get("thresholds") or {}
    metrics = loaded.get("metrics") or {}
    training_config = loaded.get("training_config") or {}
    artifacts = {
        "final_base_model": loaded["base_model"],
        "final_peak_model": loaded["peak_model"],
        "final_classifier": loaded["spike_classifier"],
        "final_p90_model": loaded.get("p90_model"),
        "best_alpha": thresholds.get("best_alpha", metrics.get("best_alpha", 0.0)),
        "best_floor": thresholds.get("best_peak_floor", metrics.get("best_peak_floor", 0.0)),
        "best_spike_threshold": thresholds.get(
            "best_spike_threshold",
            metrics.get("best_spike_threshold", training_config.get("best_spike_threshold", 0.5)),
        ),
        "base_name": metrics.get("base_model_name"),
        "peak_name": metrics.get("peak_model_name"),
        "classifier_name": metrics.get("classifier_name"),
        "metrics_df": pd.DataFrame(metrics.get("metrics") or []),
        "peak_compare_df": pd.DataFrame(metrics.get("peak_spike_metrics") or []),
        "pred_result": pd.DataFrame(),
    }
    model_version = str(metrics.get("model_version") or training_config.get("model_version") or record.get("model_version") or artifact_dir.name)
    feature_version = training_config.get("feature_version") or metrics.get("feature_version")
    return ActiveModelBundle(
        record=record,
        artifact_dir=artifact_dir,
        artifacts=artifacts,
        feature_cols=list(loaded["feature_cols"]),
        metrics=metrics,
        training_config=training_config,
        feature_version=feature_version,
        model_version=model_version,
    )


def predict_with_active_model(feature_frame: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    bundle = load_active_model_artifacts(config)
    engine = load_engine_module()
    feature_frame = feature_frame.reindex(columns=bundle.feature_cols).apply(pd.to_numeric, errors="coerce").fillna(0.0)
    base_pred = bundle.artifacts["final_base_model"].predict(feature_frame)
    peak_pred = bundle.artifacts["final_peak_model"].predict(feature_frame)
    risk_prob = engine.get_classifier_proba(bundle.artifacts["final_classifier"], feature_frame)
    peak_flags = feature_frame.get("hour", pd.Series([0] * len(feature_frame))).isin(engine.PEAK_HOURS).astype(int).to_numpy()
    load_high_flag = None
    if "forecast_load" in feature_frame.columns:
        load_high_flag = feature_frame["forecast_load"] >= feature_frame["forecast_load"].quantile(0.75)
    error_high_flag = None
    if "scenario_mae" in feature_frame.columns:
        error_high_flag = feature_frame["scenario_mae"] >= feature_frame["scenario_mae"].quantile(0.75)
    enhanced_pred, blend_weight = engine.blend_predictions(
        base_pred,
        peak_pred,
        risk_prob,
        peak_flags,
        bundle.artifacts.get("best_alpha", 0.0),
        bundle.artifacts.get("best_floor", 0.0),
        load_high_flag=load_high_flag,
        error_high_flag=error_high_flag,
        spike_threshold=bundle.artifacts.get("best_spike_threshold", 0.5),
    )
    p90_pred = None
    if bundle.artifacts.get("final_p90_model") is not None:
        try:
            p90_pred = bundle.artifacts["final_p90_model"].predict(feature_frame)
        except Exception:
            p90_pred = None
    result = pd.DataFrame(
        {
            "base_prediction": base_pred,
            "raw_base_pred": base_pred,
            "peak_prediction": peak_pred,
            "peak_pred": peak_pred,
            "spike_risk_prob": risk_prob,
            "spike_prob": risk_prob,
            "blend_weight": blend_weight,
            "dynamic_alpha": blend_weight,
            "blended_pred": enhanced_pred,
            "predicted_price": enhanced_pred,
            "model_version": bundle.model_version,
            "feature_version": bundle.feature_version,
        }
    )
    if p90_pred is not None:
        result["p90_pred"] = p90_pred
    return result
