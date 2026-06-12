from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text

from database_utils import apply_database_migrations, create_database_engine, get_database_config


def _log(log, message: str) -> None:
    if log:
        log(message)


def _risk_level(df: pd.DataFrame) -> pd.Series:
    if "risk_level" in df.columns:
        return df["risk_level"].fillna("normal").astype(str)
    if "is_spike_risk" in df.columns:
        return df["is_spike_risk"].fillna(0).astype(int).map({1: "high", 0: "normal"})
    return pd.Series(["normal"] * len(df), index=df.index)


def _bucket(series: pd.Series, low: float | None = None, high: float | None = None) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() < 10:
        return pd.Series(["unknown"] * len(series), index=series.index)
    q1 = float(numeric.quantile(0.33)) if low is None else float(low)
    q2 = float(numeric.quantile(0.66)) if high is None else float(high)
    return pd.cut(numeric, [-float("inf"), q1, q2, float("inf")], labels=["low", "mid", "high"]).astype(str).fillna("unknown")


def build_error_memory_from_prediction_tracking(config: dict[str, Any], model_version: str | None = None, log=None) -> pd.DataFrame:
    if not get_database_config(config).enabled:
        _log(log, "WARNING: 数据库未启用，无法构建模型误差记忆。")
        return pd.DataFrame()

    apply_database_migrations(config, log=log)
    engine = create_database_engine(config)
    where = "WHERE actual_price IS NOT NULL"
    params: dict[str, Any] = {}
    if model_version:
        where += " AND model_version = :model_version"
        params["model_version"] = model_version
    with engine.connect() as conn:
        df = pd.read_sql(
            text(
                f"""
                SELECT model_version, forecast_datetime, predicted_price, actual_price,
                       hour, is_peak_hour, is_spike_risk, spike_probability
                FROM prediction_tracking
                {where}
                """
            ),
            conn,
            params=params,
        )
    if df.empty:
        return pd.DataFrame()

    df["forecast_datetime"] = pd.to_datetime(df["forecast_datetime"], errors="coerce")
    df["hour"] = pd.to_numeric(df["hour"], errors="coerce").fillna(df["forecast_datetime"].dt.hour).astype(int)
    df["day_of_week"] = df["forecast_datetime"].dt.dayofweek.astype("Int64")
    df["is_peak_hour"] = pd.to_numeric(df.get("is_peak_hour", 0), errors="coerce").fillna(0).astype(int)
    df["risk_level"] = _risk_level(df)
    df["load_bucket"] = "unknown"
    df["weather_bucket"] = "unknown"
    df["predicted_price"] = pd.to_numeric(df["predicted_price"], errors="coerce")
    df["actual_price"] = pd.to_numeric(df["actual_price"], errors="coerce")
    df = df.dropna(subset=["predicted_price", "actual_price", "forecast_datetime"])
    if df.empty:
        return pd.DataFrame()
    df["bias"] = df["actual_price"] - df["predicted_price"]
    df["abs_error"] = df["bias"].abs()
    df["squared_error"] = df["bias"] ** 2
    df["over_pred"] = (df["bias"] < 0).astype(int)
    df["under_pred"] = (df["bias"] > 0).astype(int)

    group_cols = ["model_version", "hour", "day_of_week", "is_peak_hour", "risk_level", "load_bucket", "weather_bucket"]
    grouped = df.groupby(group_cols, dropna=False)
    memory = grouped.agg(
        sample_count=("bias", "size"),
        mae=("abs_error", "mean"),
        rmse=("squared_error", lambda x: float(x.mean() ** 0.5)),
        bias_mean=("bias", "mean"),
        bias_median=("bias", "median"),
        over_pred_count=("over_pred", "sum"),
        under_pred_count=("under_pred", "sum"),
    ).reset_index()
    return memory


def update_error_memory(config: dict[str, Any], model_version: str | None = None, log=None) -> int:
    if not get_database_config(config).enabled:
        _log(log, "WARNING: 数据库未启用，跳过 model_error_memory 更新。")
        return 0
    memory = build_error_memory_from_prediction_tracking(config, model_version=model_version, log=log)
    if memory.empty:
        _log(log, "WARNING: prediction_tracking 暂无可回填真实值样本，未更新误差记忆。")
        return 0
    apply_database_migrations(config, log=log)
    engine = create_database_engine(config)
    output = memory.copy()
    output["last_updated_at"] = pd.Timestamp.now()
    with engine.begin() as conn:
        if model_version:
            conn.execute(text("DELETE FROM model_error_memory WHERE model_version = :model_version"), {"model_version": model_version})
        else:
            conn.execute(text("DELETE FROM model_error_memory"))
        output.to_sql("model_error_memory", conn, if_exists="append", index=False, chunksize=500, method="multi")
    _log(log, f"SUCCESS: model_error_memory 已更新，场景数：{len(output)}。")
    return int(len(output))


def load_error_memory(config: dict[str, Any], model_version: str | None = None) -> pd.DataFrame:
    if not get_database_config(config).enabled:
        return pd.DataFrame()
    apply_database_migrations(config)
    params: dict[str, Any] = {}
    where = ""
    if model_version:
        where = "WHERE model_version = :model_version"
        params["model_version"] = model_version
    engine = create_database_engine(config)
    with engine.connect() as conn:
        return pd.read_sql(text(f"SELECT * FROM model_error_memory {where}"), conn, params=params)


def get_error_profile_for_forecast_row(row: pd.Series, memory_df: pd.DataFrame, min_samples: int = 10) -> dict[str, Any] | None:
    if memory_df is None or memory_df.empty:
        return None
    dt = pd.to_datetime(row.get("datetime"), errors="coerce")
    fallback_hour = int(dt.hour) if pd.notna(dt) else -1
    hour = int(row.get("hour", fallback_hour) if pd.notna(row.get("hour", fallback_hour)) else fallback_hour)
    day_of_week = int(dt.dayofweek) if pd.notna(dt) else None
    is_peak = int(row.get("is_peak_hour", row.get("是否高峰小时", hour in [6, 7, 8, 9, 10, 11, 18, 19, 20, 21])))
    risk = str(row.get("risk_level", "normal") or "normal")
    candidates = [
        memory_df[
            (memory_df["hour"].astype(int) == hour)
            & (memory_df["day_of_week"].astype("Int64") == day_of_week)
            & (memory_df["is_peak_hour"].astype(int) == is_peak)
            & (memory_df["risk_level"].astype(str) == risk)
        ],
        memory_df[(memory_df["hour"].astype(int) == hour) & (memory_df["is_peak_hour"].astype(int) == is_peak)],
        memory_df[memory_df["hour"].astype(int) == hour],
    ]
    for candidate in candidates:
        candidate = candidate[pd.to_numeric(candidate["sample_count"], errors="coerce").fillna(0) >= min_samples]
        if not candidate.empty:
            return candidate.sort_values("sample_count", ascending=False).iloc[0].to_dict()
    return None


def summarize_error_memory(config: dict[str, Any], model_version: str | None = None) -> dict[str, Any]:
    memory = load_error_memory(config, model_version=model_version)
    if memory.empty:
        return {
            "sample_count": 0,
            "avg_bias": None,
            "peak_avg_bias": None,
            "spike_avg_bias": None,
            "last_updated_at": "",
            "status": "empty",
        }
    sample_count = pd.to_numeric(memory["sample_count"], errors="coerce").fillna(0)
    weights = sample_count.clip(lower=1)
    avg_bias = float((pd.to_numeric(memory["bias_mean"], errors="coerce").fillna(0) * weights).sum() / weights.sum())
    peak = memory[pd.to_numeric(memory["is_peak_hour"], errors="coerce").fillna(0).astype(int) == 1]
    spike = memory[memory["risk_level"].astype(str).isin(["high", "spike"])]
    return {
        "sample_count": int(sample_count.sum()),
        "avg_bias": avg_bias,
        "peak_avg_bias": float(pd.to_numeric(peak["bias_mean"], errors="coerce").mean()) if not peak.empty else None,
        "spike_avg_bias": float(pd.to_numeric(spike["bias_mean"], errors="coerce").mean()) if not spike.empty else None,
        "last_updated_at": str(memory["last_updated_at"].max()) if "last_updated_at" in memory.columns else "",
        "status": "available",
    }
