from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
from backend.app.services.model_fact_service import DEFAULT_MODEL_DOMAIN, ModelFactError, ModelFactService
from database_utils import create_database_engine


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

    迁移必须由显式部署流程提前执行；注册不会隐式迁移或激活。
    """

    if str(status or "candidate").strip().lower() != "candidate":
        raise ModelFactError("新 artifact 只能登记为 Candidate，不能自动晋升")
    manifest = load_artifact_manifest(artifact_dir)
    metrics_path = Path(artifact_dir) / "metrics.json"
    training_path = Path(artifact_dir) / "training_config.json"
    schema_path = Path(artifact_dir) / "input_schema.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    training = json.loads(training_path.read_text(encoding="utf-8")) if training_path.exists() else {}
    input_schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else {}
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
    model_cfg = config.get("model_learning", {}) or {}
    domain = str(manifest.get("domain") or training.get("domain") or model_cfg.get("domain") or DEFAULT_MODEL_DOMAIN).strip().lower()
    target_name = str(
        manifest.get("target_name")
        or training.get("target_name")
        or input_schema.get("target_col")
        or model_cfg.get("target_name")
        or ""
    ).strip()
    if not domain or not target_name:
        raise ModelFactError("artifact 元数据缺少 domain 或 target_name")
    schema_hash = hashlib.sha256(schema_path.read_bytes()).hexdigest() if schema_path.exists() else None
    ModelFactService(create_database_engine(config)).register_candidate(
        {
            "model_id": str(manifest.get("model_id") or model_version),
            "model_version": model_version,
            "domain": domain,
            "target_name": target_name,
            "model_role": model_role,
            "artifact_id": str(manifest.get("artifact_id") or Path(artifact_dir).name),
            "artifact_path": str(Path(artifact_dir).resolve()),
            "artifact_hash": manifest.get("artifact_hash"),
            "feature_version": training.get("feature_version") or metrics.get("feature_version") or input_schema.get("feature_version"),
            "schema_hash": manifest.get("schema_hash") or schema_hash,
            "source_type": "training",
            "train_start_date": train_start_date,
            "train_end_date": train_end_date,
            "test_mae": _safe_float(metric_row.get("MAE")),
            "test_rmse": _safe_float(metric_row.get("RMSE")),
            "peak_rmse": _safe_float(_find_key(peak_row, ["高峰", "RMSE"])),
            "spike_rmse": _safe_float(_find_key(peak_row, ["尖峰", "RMSE"])),
        }
    )
    return model_version
