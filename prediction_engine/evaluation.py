from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from .legacy_engine import load_engine_module


def safe_mape(y_true, y_pred):
    return load_engine_module().safe_mape(y_true, y_pred)


def evaluate_model(y_true, y_pred, model_name: str) -> Dict:
    return load_engine_module().evaluate_regression(y_true, y_pred, model_name)


def evaluate_regression(y_true, y_pred, model_name: str) -> Dict:
    return evaluate_model(y_true, y_pred, model_name)


def identify_anomalies(pred_df: pd.DataFrame) -> pd.DataFrame:
    return load_engine_module().identify_anomalies(pred_df)


def rolling_backtest(model_df: pd.DataFrame, feature_cols: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    return load_engine_module().rolling_backtest_peak_enhanced(model_df, feature_cols)


def rolling_backtest_peak_enhanced(model_df: pd.DataFrame, feature_cols: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    return rolling_backtest(model_df, feature_cols)
