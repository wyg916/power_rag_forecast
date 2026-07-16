from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from automation_common import get_pipeline_paths, load_config
from backend.app.services.model_fact_service import DEFAULT_MODEL_DOMAIN, DEFAULT_TARGET_NAME, ModelFactService
from database_utils import create_database_engine, get_database_config
from prediction_engine.legacy_engine import load_engine_module
from model_ops.safe_model_contract import (
    ModelContractError,
    build_artifact_manifest,
    build_feature_contract,
    load_verified_candidate,
    validate_feature_batch,
)


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
    artifact_manifest: dict[str, Any]
    feature_contract: dict[str, Any]


def get_active_model_record(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    db = get_database_config(config)
    if not db.enabled:
        raise ActiveModelUnavailable("模型事实数据库未启用，无法查询 Active 模型。")
    model_cfg = config.get("model_learning", {}) or {}
    domain = str(model_cfg.get("domain") or DEFAULT_MODEL_DOMAIN).strip().lower()
    target_name = str(model_cfg.get("target_name") or DEFAULT_TARGET_NAME).strip()
    record = ModelFactService(create_database_engine(config)).get_active_model(domain, target_name)
    if not record:
        raise ActiveModelUnavailable(
            f"model_registry 中没有 {domain}/{target_name} 的 Active 模型；"
            "不会回退本地配置或自动激活 Candidate。"
        )
    return record


def validate_artifact_files(artifact_dir: str | Path) -> list[str]:
    path = Path(artifact_dir)
    return [name for name in REQUIRED_ARTIFACT_FILES if not (path / name).exists()]


def load_feature_cols(artifact_dir: str | Path) -> list[str]:
    return [item["name"] for item in build_feature_contract(artifact_dir)["features"]]


def load_model_metrics(artifact_dir: str | Path) -> dict[str, Any]:
    path = Path(artifact_dir).resolve(strict=True) / "metrics.json"
    return dict(json.loads(path.read_text(encoding="utf-8")))


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

    actual_manifest = build_artifact_manifest(artifact_dir)
    for key in ("artifact_id", "artifact_hash", "model_version", "feature_version", "schema_hash"):
        if not record.get(key):
            raise ActiveModelUnavailable(f"Active 模型缺少安全加载身份字段：{key}")
        if str(record.get(key)) != str(actual_manifest.get(key)):
            raise ActiveModelUnavailable(f"Active 模型 {key} 与 artifact 不一致，拒绝加载。")
    try:
        loaded = load_verified_candidate(
            artifact_dir,
            actual_manifest,
            authorized_dir=artifact_dir,
            output_dir=None,
        )
    except ModelContractError as exc:
        raise ActiveModelUnavailable(str(exc)) from exc
    thresholds = loaded.metadata["thresholds"]
    metrics = loaded.metadata["metrics"]
    training_config = loaded.metadata["training_config"]
    models = loaded.models
    artifacts = {
        "final_base_model": models["base_model.joblib"],
        "final_peak_model": models["peak_model.joblib"],
        "final_classifier": models["spike_classifier.joblib"],
        "final_p90_model": models.get("p90_model.joblib"),
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
    model_version = str(actual_manifest["model_version"])
    feature_version = str(actual_manifest["feature_version"])
    return ActiveModelBundle(
        record=record,
        artifact_dir=artifact_dir,
        artifacts=artifacts,
        feature_cols=[item["name"] for item in loaded.feature_contract["features"]],
        metrics=metrics,
        training_config=training_config,
        feature_version=feature_version,
        model_version=model_version,
        artifact_manifest=actual_manifest,
        feature_contract=loaded.feature_contract,
    )


def predict_with_active_model(
    feature_frame: pd.DataFrame,
    config: dict[str, Any] | None = None,
    *,
    timestamps: pd.DatetimeIndex | pd.Series | None = None,
) -> pd.DataFrame:
    bundle = load_active_model_artifacts(config)
    engine = load_engine_module()
    if timestamps is None:
        if isinstance(feature_frame.index, pd.DatetimeIndex):
            timestamps = feature_frame.index
        else:
            raise ActiveModelUnavailable("严格特征契约要求显式传入带时区的 24 小时时间索引。")
    identity = {
        "artifact_id": bundle.artifact_manifest["artifact_id"],
        "feature_version": bundle.feature_version,
        "schema_hash": bundle.feature_contract["schema_hash"],
    }
    try:
        validate_feature_batch(feature_frame, timestamps, bundle.feature_contract, identity)
    except ModelContractError as exc:
        raise ActiveModelUnavailable(str(exc)) from exc
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
        p90_pred = bundle.artifacts["final_p90_model"].predict(feature_frame)
    numeric_outputs = [np.asarray(base_pred), np.asarray(peak_pred), np.asarray(risk_prob), np.asarray(enhanced_pred)]
    if p90_pred is not None:
        numeric_outputs.append(np.asarray(p90_pred))
    if any(values.shape != (len(feature_frame),) or not np.isfinite(values).all() for values in numeric_outputs):
        raise ActiveModelUnavailable("模型输出维度异常或包含 NaN/Inf。")
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
            "artifact_id": bundle.artifact_manifest["artifact_id"],
            "schema_hash": bundle.feature_contract["schema_hash"],
        }
    )
    if p90_pred is not None:
        result["p90_pred"] = p90_pred
    return result
