from __future__ import annotations

from typing import Any

import pandas as pd

from automation_common import load_config
from model_ops.error_memory import get_error_profile_for_forecast_row, load_error_memory


PRICE_COLUMNS = [
    "predicted_price",
    "预测的未来24小时日前电价",
    "预测电价",
    "forecast_price",
    "da_price_pred",
]


def _price_column(df: pd.DataFrame) -> str:
    for column in PRICE_COLUMNS:
        if column in df.columns:
            return column
    for column in df.columns:
        name = str(column).lower()
        if "pred" in name or "预测" in str(column):
            return str(column)
    raise ValueError("无法识别预测电价字段，无法执行偏差校正。")


def _enabled(config: dict[str, Any]) -> bool:
    learning = config.get("model_learning", {}) or {}
    return bool(learning.get("bias_correction_enabled", True))


def cap_adjustment(value: float, max_abs_adjustment: float = 10.0) -> float:
    value = 0.0 if pd.isna(value) else float(value)
    return max(-float(max_abs_adjustment), min(float(max_abs_adjustment), value))


def get_bias_adjustment(
    row: pd.Series,
    memory_df: pd.DataFrame,
    min_samples: int = 10,
    max_abs_adjustment: float = 10.0,
) -> tuple[float, str]:
    profile = get_error_profile_for_forecast_row(row, memory_df, min_samples=min_samples)
    if not profile:
        return 0.0, "无足够历史误差记忆，未校正"
    sample_count = int(profile.get("sample_count") or 0)
    raw_adjustment = float(profile.get("bias_mean") or 0.0)
    adjustment = cap_adjustment(raw_adjustment, max_abs_adjustment=max_abs_adjustment)
    capped_text = "，已触发幅度上限" if abs(adjustment - raw_adjustment) > 1e-9 else ""
    reason = f"按历史误差记忆校正：样本数={sample_count}，平均偏差={raw_adjustment:.4f}{capped_text}"
    return adjustment, reason


def add_correction_columns(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    if output.empty:
        for column in ["raw_predicted_price", "bias_adjustment", "corrected_predicted_price", "correction_reason"]:
            output[column] = []
        return output
    price_col = _price_column(output)
    output["raw_predicted_price"] = pd.to_numeric(output[price_col], errors="coerce")
    if "bias_adjustment" not in output.columns:
        output["bias_adjustment"] = 0.0
    output["corrected_predicted_price"] = (output["raw_predicted_price"] + pd.to_numeric(output["bias_adjustment"], errors="coerce").fillna(0.0)).clip(lower=0.0)
    output["predicted_price"] = output["corrected_predicted_price"]
    output[price_col] = output["corrected_predicted_price"]
    if "correction_reason" not in output.columns:
        output["correction_reason"] = "未执行偏差校正"
    return output


def apply_bias_correction(
    df_forecast: pd.DataFrame,
    model_version: str,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    config = config or load_config()
    output = df_forecast.copy()
    if output.empty:
        return add_correction_columns(output)

    price_col = _price_column(output)
    output["raw_predicted_price"] = pd.to_numeric(output[price_col], errors="coerce")
    output["hour"] = pd.to_datetime(output["datetime"], errors="coerce").dt.hour
    if "is_peak_hour" not in output.columns:
        output["is_peak_hour"] = output["hour"].isin([6, 7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)
    if "risk_level" not in output.columns:
        if "spike_risk_prob" in output.columns:
            output["risk_level"] = pd.to_numeric(output["spike_risk_prob"], errors="coerce").fillna(0).map(lambda x: "high" if x >= 0.5 else "normal")
        elif "尖峰风险概率" in output.columns:
            output["risk_level"] = pd.to_numeric(output["尖峰风险概率"], errors="coerce").fillna(0).map(lambda x: "high" if x >= 0.5 else "normal")
        else:
            output["risk_level"] = "normal"

    learning = config.get("model_learning", {}) or {}
    min_samples = int(learning.get("min_error_memory_samples", 10))
    max_abs_adjustment = float(learning.get("max_bias_adjustment", 10.0))
    if not _enabled(config):
        output["bias_adjustment"] = 0.0
        output["correction_reason"] = "偏差校正已关闭"
        return add_correction_columns(output)

    memory_df = load_error_memory(config, model_version=model_version)
    if memory_df.empty:
        output["bias_adjustment"] = 0.0
        output["correction_reason"] = "无足够历史误差记忆，未校正"
        return add_correction_columns(output)

    adjustments: list[float] = []
    reasons: list[str] = []
    for _, row in output.iterrows():
        adjustment, reason = get_bias_adjustment(row, memory_df, min_samples=min_samples, max_abs_adjustment=max_abs_adjustment)
        adjustments.append(adjustment)
        reasons.append(reason)
    output["bias_adjustment"] = adjustments
    output["correction_reason"] = reasons
    return add_correction_columns(output)
