from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from database_utils import apply_database_migrations, create_database_engine
from sqlalchemy import text


def load_artifact_manifest(artifact_dir: str | Path) -> dict[str, Any]:
    path = Path(artifact_dir) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到 artifact manifest：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _preferred_metric_row(metrics: dict[str, Any]) -> dict[str, Any]:
    rows = metrics.get("metrics") or []
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    if df.empty:
        return {}
    if "模型" in df.columns:
        preferred = df[df["模型"].astype(str).str.contains("融合|增强", regex=True, na=False)]
        if not preferred.empty:
            return preferred.iloc[0].to_dict()
    if "RMSE" in df.columns:
        return df.sort_values("RMSE").iloc[0].to_dict()
    return df.iloc[0].to_dict()


def _preferred_peak_row(metrics: dict[str, Any]) -> dict[str, Any]:
    rows = metrics.get("peak_spike_metrics") or []
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    if "模型" in df.columns:
        preferred = df[df["模型"].astype(str).str.contains("融合|增强", regex=True, na=False)]
        if not preferred.empty:
            return preferred.iloc[0].to_dict()
    return df.iloc[0].to_dict()


def _find_key(row: dict[str, Any], contains: list[str]) -> Any:
    for key, value in row.items():
        if all(part in str(key) for part in contains):
            return value
    return None


def register_model_artifact(config: dict[str, Any], artifact_dir: str | Path, status: str = "candidate") -> str:
    """把模型 artifact 写入 model_registry。

    该函数先执行幂等 migrations，确保表结构存在。
    """

    apply_database_migrations(config)
    manifest = load_artifact_manifest(artifact_dir)
    metrics_path = Path(artifact_dir) / "metrics.json"
    training_path = Path(artifact_dir) / "training_config.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    training = json.loads(training_path.read_text(encoding="utf-8")) if training_path.exists() else {}
    model_version = manifest["model_version"]
    model_role = "blended"
    metric_row = _preferred_metric_row(metrics)
    peak_row = _preferred_peak_row(metrics)
    train_start_date = None
    train_end_date = None
    try:
        datasets = training.get("datasets") or []
        train_window = next((item for item in datasets if item.get("name") == "train"), None)
        if train_window:
            train_start_date = pd.to_datetime(train_window.get("start_datetime"), errors="coerce")
            train_end_date = pd.to_datetime(train_window.get("end_datetime"), errors="coerce")
            train_start_date = None if pd.isna(train_start_date) else train_start_date.date()
            train_end_date = None if pd.isna(train_end_date) else train_end_date.date()
    except Exception:
        train_start_date = None
        train_end_date = None
    engine = create_database_engine(config)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO model_registry (
                    model_version, model_role, feature_version, artifact_path,
                    status, is_active, train_start_date, train_end_date,
                    test_mae, test_rmse, peak_rmse, spike_rmse, created_at
                )
                VALUES (
                    :model_version, :model_role, :feature_version, :artifact_path,
                    :status, 0, :train_start_date, :train_end_date,
                    :test_mae, :test_rmse, :peak_rmse, :spike_rmse, CURRENT_TIMESTAMP
                )
                ON DUPLICATE KEY UPDATE
                    artifact_path = VALUES(artifact_path),
                    feature_version = VALUES(feature_version),
                    status = VALUES(status),
                    train_start_date = VALUES(train_start_date),
                    train_end_date = VALUES(train_end_date),
                    test_mae = VALUES(test_mae),
                    test_rmse = VALUES(test_rmse),
                    peak_rmse = VALUES(peak_rmse),
                    spike_rmse = VALUES(spike_rmse)
                """
            ),
            {
                "model_version": model_version,
                "model_role": model_role,
                "feature_version": training.get("feature_version") or metrics.get("feature_version"),
                "artifact_path": str(Path(artifact_dir).resolve()),
                "status": status,
                "train_start_date": train_start_date,
                "train_end_date": train_end_date,
                "test_mae": _safe_float(metric_row.get("MAE")),
                "test_rmse": _safe_float(metric_row.get("RMSE")),
                "peak_rmse": _safe_float(_find_key(peak_row, ["高峰", "RMSE"])),
                "spike_rmse": _safe_float(_find_key(peak_row, ["尖峰", "RMSE"])),
            },
        )
    return model_version
