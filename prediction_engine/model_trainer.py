from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .legacy_engine import PROJECT_ROOT, load_engine_module


def run_peak_enhanced_pipeline(train_df, val_df, test_df, feature_cols, save_validation_artifacts: bool = False):
    return load_engine_module().run_peak_enhanced_pipeline(train_df, val_df, test_df, feature_cols, save_validation_artifacts)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _dataset_window(df: pd.DataFrame | None, name: str) -> dict[str, Any]:
    if df is None or df.empty:
        return {"name": name, "rows": 0}
    result: dict[str, Any] = {"name": name, "rows": int(len(df))}
    if "datetime" in df.columns:
        dt = pd.to_datetime(df["datetime"], errors="coerce")
        result["start_datetime"] = dt.min()
        result["end_datetime"] = dt.max()
    return result


def build_feature_version(feature_cols: List[str]) -> str:
    payload = "|".join(feature_cols).encode("utf-8")
    return "features_" + hashlib.sha256(payload).hexdigest()[:12]


def _records(df: Any) -> list[dict[str, Any]]:
    if isinstance(df, pd.DataFrame):
        return df.to_dict(orient="records")
    return []


def save_model_artifacts(
    artifacts: Dict[str, Any],
    feature_cols: List[str],
    train_df: pd.DataFrame | None = None,
    val_df: pd.DataFrame | None = None,
    test_df: pd.DataFrame | None = None,
    output_root: str | Path | None = None,
    run_id: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """保存阶段二模型 artifact。

    产物目录包含 joblib 模型、特征列、训练窗口、核心指标、阈值、输入 schema
    和模型说明，为后续 model_registry、自优化和回滚打基础。
    """

    try:
        import joblib
    except Exception as exc:  # pragma: no cover - requirements 缺失时给出明确错误
        raise RuntimeError("保存模型 artifact 需要安装 joblib，请先安装 requirements.txt") from exc

    model_version = run_id or os.environ.get("PIPELINE_RUN_ID") or datetime.now().strftime("model_%Y%m%d_%H%M%S")
    if not str(model_version).startswith("model_"):
        model_version = "model_" + str(model_version)
    root = Path(output_root) if output_root else PROJECT_ROOT / "model_artifacts"
    artifact_dir = root / model_version
    artifact_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(artifacts.get("final_base_model"), artifact_dir / "base_model.joblib")
    joblib.dump(artifacts.get("final_peak_model"), artifact_dir / "peak_model.joblib")
    joblib.dump(artifacts.get("final_classifier"), artifact_dir / "spike_classifier.joblib")
    optional_files: list[str] = []
    if artifacts.get("final_p90_model") is not None:
        joblib.dump(artifacts.get("final_p90_model"), artifact_dir / "p90_model.joblib")
        optional_files.append("p90_model.joblib")

    feature_version = build_feature_version(list(feature_cols))
    _write_json(artifact_dir / "feature_cols.json", list(feature_cols))
    _write_json(
        artifact_dir / "training_config.json",
        {
            "model_version": model_version,
            "feature_version": feature_version,
            "target_col": "da_price",
            "datasets": [
                _dataset_window(train_df, "train"),
                _dataset_window(val_df, "validation"),
                _dataset_window(test_df, "test"),
            ],
            "base_model_name": artifacts.get("base_name"),
            "peak_model_name": artifacts.get("peak_name"),
            "classifier_name": artifacts.get("classifier_name"),
            "best_spike_threshold": artifacts.get("best_spike_threshold"),
            "has_p90_model": artifacts.get("final_p90_model") is not None,
            "extra_metadata": extra_metadata or {},
        },
    )
    _write_json(
        artifact_dir / "metrics.json",
        {
            "model_version": model_version,
            "base_model_name": artifacts.get("base_name"),
            "peak_model_name": artifacts.get("peak_name"),
            "classifier_name": artifacts.get("classifier_name"),
            "best_alpha": artifacts.get("best_alpha"),
            "best_peak_floor": artifacts.get("best_floor"),
            "best_spike_threshold": artifacts.get("best_spike_threshold"),
            "has_p90_model": artifacts.get("final_p90_model") is not None,
            "metrics": _records(artifacts.get("metrics_df")),
            "peak_spike_metrics": _records(artifacts.get("peak_compare_df")),
            "validation_summary": _records(artifacts.get("validation_summary")),
        },
    )
    _write_json(
        artifact_dir / "thresholds.json",
        {
            "best_alpha": artifacts.get("best_alpha"),
            "best_peak_floor": artifacts.get("best_floor"),
            "best_spike_threshold": artifacts.get("best_spike_threshold"),
            "spike_thresholds": artifacts.get("train_thresholds", {}),
        },
    )
    _write_json(
        artifact_dir / "input_schema.json",
        {
            "target_col": "da_price",
            "feature_version": feature_version,
            "feature_count": len(feature_cols),
            "features": [{"name": name, "dtype": "numeric"} for name in feature_cols],
        },
    )
    _write_json(
        artifact_dir / "manifest.json",
        {
            "model_version": model_version,
            "artifact_dir": str(artifact_dir),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "files": [
                "base_model.joblib",
                "peak_model.joblib",
                "spike_classifier.joblib",
                "feature_cols.json",
                "training_config.json",
                "metrics.json",
                "thresholds.json",
                "model_card.md",
                "input_schema.json",
            ]
            + optional_files,
        },
    )
    model_card = f"""# 模型版本说明

- 模型版本：{model_version}
- 特征版本：{feature_version}
- 基础模型：{artifacts.get("base_name")}
- 高峰专项模型：{artifacts.get("peak_name")}
- 尖峰分类器：{artifacts.get("classifier_name")}
- 融合参数 alpha：{artifacts.get("best_alpha")}
- 高峰 floor：{artifacts.get("best_floor")}

## 用途

用于 PJM/DOM 日前电价未来 24 小时预测，并增强高峰与尖峰风险时段的拟合能力。

## 适用范围

适用于当前项目主表字段、特征工程版本和训练窗口。预测阶段必须使用 `feature_cols.json` 中相同的特征列顺序。

## 已知限制

该 artifact 仍来自 v4_fix1 兼容训练流程；阶段三将进一步接入 model_registry、prediction_tracking、真实值回填和候选模型上线控制。
"""
    (artifact_dir / "model_card.md").write_text(model_card, encoding="utf-8")
    return artifact_dir


def load_model_artifacts(artifact_dir: str | Path) -> dict[str, Any]:
    try:
        import joblib
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("加载模型 artifact 需要安装 joblib，请先安装 requirements.txt") from exc

    path = Path(artifact_dir)
    if not path.exists():
        raise FileNotFoundError(f"模型 artifact 目录不存在：{path}")

    def read_json(name: str) -> Any:
        return json.loads((path / name).read_text(encoding="utf-8"))

    payload = {
        "artifact_dir": path,
        "base_model": joblib.load(path / "base_model.joblib"),
        "peak_model": joblib.load(path / "peak_model.joblib"),
        "spike_classifier": joblib.load(path / "spike_classifier.joblib"),
        "feature_cols": read_json("feature_cols.json"),
        "training_config": read_json("training_config.json"),
        "metrics": read_json("metrics.json"),
        "thresholds": read_json("thresholds.json"),
        "input_schema": read_json("input_schema.json"),
    }
    p90_path = path / "p90_model.joblib"
    if p90_path.exists():
        payload["p90_model"] = joblib.load(p90_path)
    return payload
