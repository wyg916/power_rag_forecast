from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from database_utils import apply_database_migrations, create_database_engine, get_database_config
from model_ops.model_registry import load_artifact_manifest

def build_prediction_tracking_frame(
    future_result: pd.DataFrame,
    run_id: str,
    model_version: str,
    feature_version: str | None = None,
) -> pd.DataFrame:
    """把未来 24 小时预测结果转换为 prediction_tracking 可写入结构。"""

    if future_result is None or future_result.empty:
        return pd.DataFrame()
    df = future_result.copy()
    prediction_col = next(
        (col for col in ["predicted_price", "corrected_predicted_price", "预测的未来24小时日前电价", "forecast_price", "da_price_pred"] if col in df.columns),
        "",
    )
    if not prediction_col:
        candidates = [c for c in df.columns if "预测" in str(c) or "pred" in str(c).lower()]
        if not candidates:
            raise ValueError("无法识别预测结果字段")
        prediction_col = candidates[0]
    output = pd.DataFrame(
        {
            "run_id": run_id,
            "forecast_datetime": pd.to_datetime(df["datetime"], errors="coerce"),
            "generated_at": pd.Timestamp.now(),
            "predicted_price": pd.to_numeric(df[prediction_col], errors="coerce"),
            "hour": pd.to_datetime(df["datetime"], errors="coerce").dt.hour,
            "model_version": model_version,
            "feature_version": feature_version,
        }
    )
    if "尖峰风险概率" in df.columns:
        output["spike_probability"] = pd.to_numeric(df["尖峰风险概率"], errors="coerce")
        output["is_spike_risk"] = (output["spike_probability"].fillna(0) >= 0.5).astype(int)
    if "是否高峰小时" in df.columns:
        output["is_peak_hour"] = pd.to_numeric(df["是否高峰小时"], errors="coerce").fillna(0).astype(int)
    else:
        output["is_peak_hour"] = output["hour"].isin([6, 7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)
    return output


def load_future_result_excel(path: str | Path) -> pd.DataFrame:
    return pd.read_excel(path)


def write_prediction_tracking(
    config: dict[str, Any],
    tracking_df: pd.DataFrame,
    run_id: str,
    log=None,
) -> int:
    """把正式预测结果写入 prediction_tracking。

    同一 run_id 重复执行时先清理该 run_id 的旧记录，保证任务重跑幂等。
    """

    if tracking_df is None or tracking_df.empty:
        return 0
    if not get_database_config(config).enabled:
        if log:
            log("数据库未启用，跳过 prediction_tracking 写入。")
        return 0

    apply_database_migrations(config, log=log)
    output = tracking_df.copy()
    engine = create_database_engine(config)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM prediction_tracking WHERE run_id = :run_id"), {"run_id": run_id})
        output.to_sql("prediction_tracking", conn, if_exists="append", index=False, chunksize=500, method="multi")
    if log:
        log(f"prediction_tracking 已写入 {len(output)} 条记录。")
    return int(len(output))


def track_future_prediction_file(
    config: dict[str, Any],
    future_result_path: str | Path,
    artifact_dir: str | Path,
    run_id: str,
    log=None,
) -> int:
    future_result = load_future_result_excel(future_result_path)
    manifest = load_artifact_manifest(artifact_dir)
    training_config_path = Path(artifact_dir) / "training_config.json"
    feature_version = None
    if training_config_path.exists():
        import json

        feature_version = json.loads(training_config_path.read_text(encoding="utf-8")).get("feature_version")
    tracking_df = build_prediction_tracking_frame(
        future_result,
        run_id=run_id,
        model_version=manifest["model_version"],
        feature_version=feature_version,
    )
    return write_prediction_tracking(config, tracking_df, run_id=run_id, log=log)
