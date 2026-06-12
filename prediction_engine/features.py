from __future__ import annotations

from typing import List

import pandas as pd

from .legacy_engine import load_engine_module


def standardize_datetime_frame(df: pd.DataFrame, dt_col: str = "datetime") -> pd.DataFrame:
    """统一 datetime 字段类型、排序和去重，供数据标准化测试与服务层复用。"""

    if dt_col not in df.columns:
        raise ValueError(f"缺少时间字段：{dt_col}")
    output = df.copy()
    output[dt_col] = pd.to_datetime(output[dt_col], errors="coerce")
    output = output.dropna(subset=[dt_col]).sort_values(dt_col).drop_duplicates(subset=[dt_col])
    return output.reset_index(drop=True)


def create_time_features(df: pd.DataFrame, dt_col: str = "datetime") -> pd.DataFrame:
    return load_engine_module().create_time_features(df, dt_col=dt_col)


def create_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    return load_engine_module().create_lag_features(df)


def create_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    return load_engine_module().create_rolling_features(df)


def create_ewm_features(df: pd.DataFrame) -> pd.DataFrame:
    return load_engine_module().create_ewm_features(df)


def create_history_group_features(df: pd.DataFrame) -> pd.DataFrame:
    return load_engine_module().create_history_group_features(df)


def add_safe_business_features(df: pd.DataFrame) -> pd.DataFrame:
    return load_engine_module().add_safe_business_features(df)


def leakage_check_report(df: pd.DataFrame) -> pd.DataFrame:
    return load_engine_module().leakage_check_report(df)


def build_feature_list(df: pd.DataFrame) -> List[str]:
    return load_engine_module().build_feature_list(df)


def run_full_feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    return load_engine_module().run_full_feature_engineering(df)


def get_leakage_banned_raw_columns() -> list[str]:
    return list(load_engine_module().LEAKAGE_BANNED_RAW_COLS)


# 文档建议函数名兼容别名。
build_time_features = create_time_features
build_lag_features = create_lag_features
build_rolling_features = create_rolling_features
build_forecast_features = run_full_feature_engineering
filter_leakage_features = build_feature_list
