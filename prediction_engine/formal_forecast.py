from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .legacy_engine import load_engine_module


def generate_forward_forecast(history_df: pd.DataFrame, feature_cols: List[str], artifacts: Dict, model_df: pd.DataFrame):
    return load_engine_module().generate_formal_forward_forecast(history_df, feature_cols, artifacts, model_df)


def generate_formal_forward_forecast(history_df: pd.DataFrame, feature_cols: List[str], artifacts: Dict, model_df: pd.DataFrame):
    return generate_forward_forecast(history_df, feature_cols, artifacts, model_df)


def _pick_prediction_column(df: pd.DataFrame) -> str:
    preferred = [
        "预测的未来24小时日前电价",
        "高峰增强融合预测值",
        "预测值",
        "predicted_price",
        "prediction",
    ]
    for column in preferred:
        if column in df.columns:
            return column
    for column in df.columns:
        name = str(column).lower()
        if "预测" in str(column) or "pred" in name:
            return str(column)
    raise ValueError("无法识别预测值字段")


def _build_residual_frame(test_prediction_df: pd.DataFrame) -> pd.DataFrame:
    if test_prediction_df is None or test_prediction_df.empty:
        return pd.DataFrame(columns=["hour", "residual"])

    df = test_prediction_df.copy()
    pred_col = _pick_prediction_column(df)
    if "datetime" in df.columns and "hour" not in df.columns:
        df["hour"] = pd.to_datetime(df["datetime"], errors="coerce").dt.hour
    if "hour" not in df.columns:
        df["hour"] = -1

    if "真实值" in df.columns:
        residual = pd.to_numeric(df["真实值"], errors="coerce") - pd.to_numeric(df[pred_col], errors="coerce")
    elif "actual_price" in df.columns:
        residual = pd.to_numeric(df["actual_price"], errors="coerce") - pd.to_numeric(df[pred_col], errors="coerce")
    elif "预测误差" in df.columns:
        residual = -pd.to_numeric(df["预测误差"], errors="coerce")
    else:
        return pd.DataFrame(columns=["hour", "residual"])

    output = pd.DataFrame({"hour": pd.to_numeric(df["hour"], errors="coerce").fillna(-1).astype(int), "residual": residual})
    return output.replace([np.inf, -np.inf], np.nan).dropna(subset=["residual"])


def add_residual_prediction_intervals(
    future_result: pd.DataFrame,
    test_prediction_df: pd.DataFrame,
    low_quantile: float = 0.1,
    high_quantile: float = 0.9,
) -> pd.DataFrame:
    """基于测试集残差分布，为正式前瞻点预测增加 P10/P90 区间。

    该方法是阶段二短期可落地方案：不改变现有点预测，只把历史误差分布
    叠加到未来 24 小时预测上，给业务侧一个可解释的风险范围。
    """

    if future_result is None or future_result.empty:
        return future_result

    output = future_result.copy()
    prediction_col = _pick_prediction_column(output)
    residuals = _build_residual_frame(test_prediction_df)
    if residuals.empty:
        output["预测下界_P10"] = pd.NA
        output["预测上界_P90"] = pd.NA
        output["预测区间宽度"] = pd.NA
        output["预测区间方法"] = "未生成：测试残差不可用"
        return output

    if "datetime" in output.columns:
        output["_interval_hour"] = pd.to_datetime(output["datetime"], errors="coerce").dt.hour.fillna(-1).astype(int)
    elif "hour" in output.columns:
        output["_interval_hour"] = pd.to_numeric(output["hour"], errors="coerce").fillna(-1).astype(int)
    else:
        output["_interval_hour"] = -1

    global_low = float(residuals["residual"].quantile(low_quantile))
    global_high = float(residuals["residual"].quantile(high_quantile))
    grouped = residuals.groupby("hour")["residual"].quantile([low_quantile, high_quantile]).unstack()

    lows: list[float] = []
    highs: list[float] = []
    for hour in output["_interval_hour"]:
        if hour in grouped.index:
            low = float(grouped.loc[hour].get(low_quantile, global_low))
            high = float(grouped.loc[hour].get(high_quantile, global_high))
        else:
            low, high = global_low, global_high
        lows.append(low)
        highs.append(high)

    point = pd.to_numeric(output[prediction_col], errors="coerce")
    output["预测下界_P10"] = point + pd.Series(lows, index=output.index)
    output["预测上界_P90"] = point + pd.Series(highs, index=output.index)
    output["预测区间宽度"] = output["预测上界_P90"] - output["预测下界_P10"]
    output["预测区间方法"] = "残差分布法_按小时P10_P90"
    return output.drop(columns=["_interval_hour"])
