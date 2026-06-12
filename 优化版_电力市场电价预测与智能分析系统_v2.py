
# -*- coding: utf-8 -*-
"""
项目名称：基于公开电力市场数据的电价预测与智能分析系统
当前版本：优化版（保留原核心功能 + 增强异常波动识别 + 滚动回测 + 模型稳健优化）

优化说明：
1）保留原有核心功能：数据读取、数据质量检查、EDA、特征工程、模型评估、预测结果输出、图表输出；
2）新增验证集模型选择，优先选择更优模型配置；
3）新增更丰富的时序特征、滚动特征、EWM特征、分组历史均值特征；
4）新增异常波动识别模块，定位尖峰时段和高误差样本；
5）新增滚动回测模块，评估模型在多个时间窗口下的稳定性；
6）保留未来24小时演示版预测输出；
7）全部结果保存到指定目录。
"""

import os
import sys
import math
import warnings
from typing import List, Dict, Tuple

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression

# =========================
# 路径配置
# =========================
DATA_DIR = r"E:\智能运营分析项目\output"
RESULT_DIR = r"E:\智能运营分析项目\结果-1"

MASTER_FILE = os.path.join(DATA_DIR, "master_table.xlsx")

FIG_DIR = os.path.join(RESULT_DIR, "图表")
MODEL_DIR = os.path.join(RESULT_DIR, "模型结果")
TABLE_DIR = os.path.join(RESULT_DIR, "结果表")
LOG_DIR = os.path.join(RESULT_DIR, "日志")

for path in [RESULT_DIR, FIG_DIR, MODEL_DIR, TABLE_DIR, LOG_DIR]:
    os.makedirs(path, exist_ok=True)

# =========================
# 中文字体设置
# =========================
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# =========================
# 全局配置
# =========================
RANDOM_STATE = 42
TEST_DAYS = 30
VAL_DAYS = 30
ROLLING_BACKTEST_FOLDS = 6
ROLLING_BACKTEST_FOLD_DAYS = 7
MIN_TRAIN_DAYS_FOR_BACKTEST = 180
ANOMALY_MIN_ABS_ERROR = 30.0   # 绝对误差最小阈值下限
TOP_N_FEATURES = 25

# =========================
# 工具函数
# =========================
def log_print(msg: str):
    print(msg)
    with open(os.path.join(LOG_DIR, "运行日志.txt"), "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def save_fig(fig, filepath: str):
    fig.tight_layout()
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)


def safe_mape(y_true, y_pred):
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)
    denominator = np.where(np.abs(y_true) < 1e-6, 1e-6, np.abs(y_true))
    return np.mean(np.abs((y_true - y_pred) / denominator)) * 100


def evaluate_regression(y_true, y_pred, model_name: str):
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = math.sqrt(mean_squared_error(y_true, y_pred))
    mape = safe_mape(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    return {
        "模型": model_name,
        "MAE": mae,
        "RMSE": rmse,
        "MAPE(%)": mape,
        "R2": r2
    }


def expanding_group_mean(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding().mean()


def expanding_group_std(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding().std()


def create_time_features(df: pd.DataFrame, dt_col: str = "datetime") -> pd.DataFrame:
    df = df.copy()
    df["hour"] = df[dt_col].dt.hour
    df["day_of_week"] = df[dt_col].dt.dayofweek
    df["month"] = df[dt_col].dt.month
    df["day"] = df[dt_col].dt.day
    df["year"] = df[dt_col].dt.year
    df["day_of_year"] = df[dt_col].dt.dayofyear
    df["week_of_year"] = df[dt_col].dt.isocalendar().week.astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_month_start"] = df[dt_col].dt.is_month_start.astype(int)
    df["is_month_end"] = df[dt_col].dt.is_month_end.astype(int)

    # 周期特征
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["doy_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)

    return df


def create_lag_features(df: pd.DataFrame, target_col: str = "da_price") -> pd.DataFrame:
    df = df.copy()

    lag_features = {
        target_col: [1, 2, 3, 6, 12, 18, 24, 25, 48, 72, 96, 168, 169],
        "forecast_load": [1, 2, 24, 25, 48, 168],
        "actual_load": [1, 2, 24, 25, 48, 168],
        "temperature": [1, 2, 24, 48, 168],
        "wind_speed": [1, 24, 48],
        "precipitation": [1, 24, 48],
        "price_spread_rt_minus_da": [1, 24, 168]
    }

    for col, lags in lag_features.items():
        if col in df.columns:
            for lag in lags:
                df[f"{col}_lag_{lag}"] = df[col].shift(lag)

    return df


def create_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rolling_config = {
        "da_price": [6, 12, 24, 48, 168],
        "forecast_load": [24, 48, 168],
        "actual_load": [24, 48, 168],
        "temperature": [24, 48, 168]
    }

    for col, windows in rolling_config.items():
        if col in df.columns:
            for w in windows:
                shifted = df[col].shift(1)
                df[f"{col}_roll_mean_{w}"] = shifted.rolling(window=w).mean()
                df[f"{col}_roll_std_{w}"] = shifted.rolling(window=w).std()
                df[f"{col}_roll_min_{w}"] = shifted.rolling(window=w).min()
                df[f"{col}_roll_max_{w}"] = shifted.rolling(window=w).max()
                df[f"{col}_roll_median_{w}"] = shifted.rolling(window=w).median()

    return df


def create_ewm_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    ewm_config = {
        "da_price": [6, 24, 168],
        "forecast_load": [24, 168],
        "actual_load": [24, 168],
        "temperature": [24, 168]
    }

    for col, spans in ewm_config.items():
        if col in df.columns:
            for span in spans:
                shifted = df[col].shift(1)
                df[f"{col}_ewm_mean_{span}"] = shifted.ewm(span=span, adjust=False).mean()
                df[f"{col}_ewm_std_{span}"] = shifted.ewm(span=span, adjust=False).std()

    return df


def create_history_group_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "da_price" in df.columns:
        if "hour" in df.columns:
            df["da_price_hist_hour_mean"] = df.groupby("hour")["da_price"].transform(expanding_group_mean)
            df["da_price_hist_hour_std"] = df.groupby("hour")["da_price"].transform(expanding_group_std)

        if "day_of_week" in df.columns:
            df["da_price_hist_dow_mean"] = df.groupby("day_of_week")["da_price"].transform(expanding_group_mean)

        if "month" in df.columns:
            df["da_price_hist_month_mean"] = df.groupby("month")["da_price"].transform(expanding_group_mean)

        if "is_weekend" in df.columns:
            df["da_price_hist_weekend_mean"] = df.groupby("is_weekend")["da_price"].transform(expanding_group_mean)

    return df


def add_business_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "temperature" in df.columns:
        df["temperature_sq"] = df["temperature"] ** 2
        df["cooling_degree"] = np.maximum(df["temperature"] - 22, 0)
        df["heating_degree"] = np.maximum(18 - df["temperature"], 0)
        df["temp_change_1h"] = df["temperature"] - df["temperature"].shift(1)
        df["temp_change_24h"] = df["temperature"] - df["temperature"].shift(24)

    if "forecast_load" in df.columns and "actual_load" in df.columns:
        df["load_gap"] = df["forecast_load"] - df["actual_load"]
        df["load_ratio"] = df["forecast_load"] / np.where(np.abs(df["actual_load"]) < 1e-6, 1e-6, df["actual_load"])

    if "forecast_evaluated_at" in df.columns and "datetime" in df.columns:
        try:
            df["forecast_issue_lead_hours"] = (
                (pd.to_datetime(df["datetime"]) - pd.to_datetime(df["forecast_evaluated_at"]))
                .dt.total_seconds() / 3600.0
            )
        except Exception:
            pass

    if "rt_price" in df.columns and "da_price" in df.columns:
        df["price_spread_rt_minus_da"] = df["rt_price"] - df["da_price"]

    if "hour" in df.columns:
        df["is_peak_hour"] = df["hour"].isin([6, 7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)
        df["is_valley_hour"] = df["hour"].isin([0, 1, 2, 3, 4, 5]).astype(int)

    if "da_price" in df.columns:
        df["price_change_1h"] = df["da_price"] - df["da_price"].shift(1)
        df["price_change_24h"] = df["da_price"] - df["da_price"].shift(24)
        df["price_ratio_1h"] = df["da_price"] / np.where(np.abs(df["da_price"].shift(1)) < 1e-6, 1e-6, df["da_price"].shift(1))
        df["price_ratio_24h"] = df["da_price"] / np.where(np.abs(df["da_price"].shift(24)) < 1e-6, 1e-6, df["da_price"].shift(24))

    if "forecast_load" in df.columns:
        df["forecast_load_change_1h"] = df["forecast_load"] - df["forecast_load"].shift(1)
        df["forecast_load_change_24h"] = df["forecast_load"] - df["forecast_load"].shift(24)

    return df


def build_feature_list(df: pd.DataFrame) -> List[str]:
    candidate_features = [
        # 时间特征
        "hour", "day_of_week", "month", "day", "year", "day_of_year", "week_of_year",
        "is_weekend", "is_month_start", "is_month_end",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos", "doy_sin", "doy_cos",

        # 业务特征
        "forecast_load", "temperature", "wind_speed", "precipitation",
        "temperature_sq", "cooling_degree", "heating_degree",
        "load_gap", "load_ratio", "forecast_issue_lead_hours",
        "is_peak_hour", "is_valley_hour", "temp_change_1h", "temp_change_24h",
        "forecast_load_change_1h", "forecast_load_change_24h",

        # 历史统计特征
        "da_price_hist_hour_mean", "da_price_hist_hour_std",
        "da_price_hist_dow_mean", "da_price_hist_month_mean", "da_price_hist_weekend_mean",

        # 历史价格滞后
        "da_price_lag_1", "da_price_lag_2", "da_price_lag_3", "da_price_lag_6", "da_price_lag_12",
        "da_price_lag_18", "da_price_lag_24", "da_price_lag_25", "da_price_lag_48",
        "da_price_lag_72", "da_price_lag_96", "da_price_lag_168", "da_price_lag_169",

        # 价格变化特征（仅基于历史）
        "price_change_1h", "price_change_24h", "price_ratio_1h", "price_ratio_24h",
        "price_spread_rt_minus_da_lag_1", "price_spread_rt_minus_da_lag_24", "price_spread_rt_minus_da_lag_168",

        # 负荷滞后
        "forecast_load_lag_1", "forecast_load_lag_2", "forecast_load_lag_24",
        "forecast_load_lag_25", "forecast_load_lag_48", "forecast_load_lag_168",
        "actual_load_lag_1", "actual_load_lag_2", "actual_load_lag_24",
        "actual_load_lag_25", "actual_load_lag_48", "actual_load_lag_168",

        # 天气滞后
        "temperature_lag_1", "temperature_lag_2", "temperature_lag_24", "temperature_lag_48", "temperature_lag_168",
        "wind_speed_lag_1", "wind_speed_lag_24", "wind_speed_lag_48",
        "precipitation_lag_1", "precipitation_lag_24", "precipitation_lag_48",

        # 滚动统计
        "da_price_roll_mean_6", "da_price_roll_std_6", "da_price_roll_median_6",
        "da_price_roll_mean_12", "da_price_roll_std_12", "da_price_roll_median_12",
        "da_price_roll_mean_24", "da_price_roll_std_24", "da_price_roll_min_24", "da_price_roll_max_24", "da_price_roll_median_24",
        "da_price_roll_mean_48", "da_price_roll_std_48", "da_price_roll_median_48",
        "da_price_roll_mean_168", "da_price_roll_std_168", "da_price_roll_min_168", "da_price_roll_max_168", "da_price_roll_median_168",

        "forecast_load_roll_mean_24", "forecast_load_roll_std_24", "forecast_load_roll_median_24",
        "forecast_load_roll_mean_48", "forecast_load_roll_std_48",
        "forecast_load_roll_mean_168", "forecast_load_roll_std_168",

        "actual_load_roll_mean_24", "actual_load_roll_std_24", "actual_load_roll_mean_168", "actual_load_roll_std_168",
        "temperature_roll_mean_24", "temperature_roll_std_24", "temperature_roll_mean_168", "temperature_roll_std_168",

        # EWM
        "da_price_ewm_mean_6", "da_price_ewm_std_6",
        "da_price_ewm_mean_24", "da_price_ewm_std_24",
        "da_price_ewm_mean_168", "da_price_ewm_std_168",
        "forecast_load_ewm_mean_24", "forecast_load_ewm_std_24",
        "forecast_load_ewm_mean_168", "forecast_load_ewm_std_168",
        "actual_load_ewm_mean_24", "actual_load_ewm_std_24",
        "actual_load_ewm_mean_168", "actual_load_ewm_std_168",
        "temperature_ewm_mean_24", "temperature_ewm_std_24",
        "temperature_ewm_mean_168", "temperature_ewm_std_168"
    ]

    final_features = [f for f in candidate_features if f in df.columns]
    return final_features


def try_import_xgboost():
    try:
        from xgboost import XGBRegressor
        return XGBRegressor
    except Exception:
        return None


def try_import_lightgbm():
    try:
        from lightgbm import LGBMRegressor
        return LGBMRegressor
    except Exception:
        return None


def get_model_candidates() -> List[Dict]:
    candidates = []

    XGBRegressor = try_import_xgboost()
    if XGBRegressor is not None:
        candidates.append({
            "name": "XGBoost_raw",
            "use_log_target": False,
            "builder": lambda: XGBRegressor(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.04,
                subsample=0.85,
                colsample_bytree=0.85,
                min_child_weight=3,
                reg_alpha=0.0,
                reg_lambda=1.0,
                objective="reg:squarederror",
                random_state=RANDOM_STATE,
                n_jobs=-1
            )
        })
        candidates.append({
            "name": "XGBoost_log",
            "use_log_target": True,
            "builder": lambda: XGBRegressor(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.04,
                subsample=0.85,
                colsample_bytree=0.85,
                min_child_weight=3,
                reg_alpha=0.0,
                reg_lambda=1.0,
                objective="reg:squarederror",
                random_state=RANDOM_STATE,
                n_jobs=-1
            )
        })

    LGBMRegressor = try_import_lightgbm()
    if LGBMRegressor is not None:
        candidates.append({
            "name": "LightGBM_raw",
            "use_log_target": False,
            "builder": lambda: LGBMRegressor(
                n_estimators=500,
                learning_rate=0.04,
                num_leaves=31,
                subsample=0.85,
                colsample_bytree=0.85,
                random_state=RANDOM_STATE
            )
        })
        candidates.append({
            "name": "LightGBM_log",
            "use_log_target": True,
            "builder": lambda: LGBMRegressor(
                n_estimators=500,
                learning_rate=0.04,
                num_leaves=31,
                subsample=0.85,
                colsample_bytree=0.85,
                random_state=RANDOM_STATE
            )
        })

    candidates.append({
        "name": "HistGB_raw",
        "use_log_target": False,
        "builder": lambda: HistGradientBoostingRegressor(
            learning_rate=0.04,
            max_depth=8,
            max_iter=400,
            l2_regularization=0.0,
            random_state=RANDOM_STATE
        )
    })
    candidates.append({
        "name": "HistGB_log",
        "use_log_target": True,
        "builder": lambda: HistGradientBoostingRegressor(
            learning_rate=0.04,
            max_depth=8,
            max_iter=400,
            l2_regularization=0.0,
            random_state=RANDOM_STATE
        )
    })
    candidates.append({
        "name": "RandomForest_raw",
        "use_log_target": False,
        "builder": lambda: RandomForestRegressor(
            n_estimators=500,
            max_depth=14,
            min_samples_leaf=2,
            random_state=RANDOM_STATE,
            n_jobs=-1
        )
    })

    return candidates


def fit_predict_with_config(model_cfg: Dict, X_train: pd.DataFrame, y_train: pd.Series, X_pred: pd.DataFrame):
    model = model_cfg["builder"]()
    if model_cfg.get("use_log_target", False):
        y_train_log = np.log1p(np.clip(y_train, a_min=0, a_max=None))
        model.fit(X_train, y_train_log)
        pred_log = model.predict(X_pred)
        pred = np.expm1(pred_log)
    else:
        model.fit(X_train, y_train)
        pred = model.predict(X_pred)

    pred = np.clip(np.array(pred, dtype=float), a_min=0, a_max=None)
    return model, pred


def select_best_model_by_validation(X_train, y_train, X_val, y_val) -> Tuple[Dict, pd.DataFrame]:
    candidate_results = []
    candidates = get_model_candidates()

    log_print("=" * 80)
    log_print("开始在验证集上选择最优模型配置...")

    for cfg in candidates:
        try:
            _, val_pred = fit_predict_with_config(cfg, X_train, y_train, X_val)
            metrics = evaluate_regression(y_val, val_pred, cfg["name"])
            candidate_results.append(metrics)
            log_print(f"验证完成：{cfg['name']} -> RMSE={metrics['RMSE']:.6f}, MAE={metrics['MAE']:.6f}, MAPE={metrics['MAPE(%)']:.6f}, R2={metrics['R2']:.6f}")
        except Exception as e:
            log_print(f"模型 {cfg['name']} 验证失败，原因：{e}")

    if len(candidate_results) == 0:
        raise RuntimeError("没有任何候选模型训练成功，请检查依赖或数据。")

    candidate_df = pd.DataFrame(candidate_results).sort_values(["RMSE", "MAE", "MAPE(%)"], ascending=[True, True, True]).reset_index(drop=True)
    best_name = candidate_df.iloc[0]["模型"]

    best_cfg = None
    for cfg in candidates:
        if cfg["name"] == best_name:
            best_cfg = cfg
            break

    if best_cfg is None:
        raise RuntimeError("未能根据验证结果定位最佳模型配置。")

    return best_cfg, candidate_df


def get_feature_importance(model, feature_names: List[str]) -> pd.DataFrame:
    if hasattr(model, "feature_importances_"):
        imp = pd.DataFrame({
            "特征": feature_names,
            "重要性": model.feature_importances_
        }).sort_values("重要性", ascending=False)
        return imp
    elif hasattr(model, "coef_"):
        imp = pd.DataFrame({
            "特征": feature_names,
            "重要性": np.abs(model.coef_)
        }).sort_values("重要性", ascending=False)
        return imp
    else:
        return pd.DataFrame(columns=["特征", "重要性"])


def rolling_backtest(model_cfg: Dict,
                     model_df: pd.DataFrame,
                     feature_cols: List[str],
                     target_col: str,
                     fold_days: int = 7,
                     n_folds: int = 6,
                     min_train_days: int = 180) -> Tuple[pd.DataFrame, pd.DataFrame]:
    log_print("=" * 80)
    log_print("开始滚动回测...")

    model_df = model_df.sort_values("datetime").reset_index(drop=True)
    end_dt = model_df["datetime"].max()
    start_bt = end_dt - pd.Timedelta(days=fold_days * n_folds)

    bt_metrics = []
    bt_preds = []

    for i in range(n_folds):
        fold_start = start_bt + pd.Timedelta(days=fold_days * i)
        fold_end = fold_start + pd.Timedelta(days=fold_days)

        train_mask = model_df["datetime"] < fold_start
        test_mask = (model_df["datetime"] >= fold_start) & (model_df["datetime"] < fold_end)

        train_df = model_df.loc[train_mask].copy()
        test_df = model_df.loc[test_mask].copy()

        if train_df.empty or test_df.empty:
            continue

        train_span_days = (train_df["datetime"].max() - train_df["datetime"].min()).days
        if train_span_days < min_train_days:
            continue

        X_train_bt = train_df[feature_cols]
        y_train_bt = train_df[target_col]
        X_test_bt = test_df[feature_cols]
        y_test_bt = test_df[target_col]

        try:
            _, bt_pred = fit_predict_with_config(model_cfg, X_train_bt, y_train_bt, X_test_bt)
            m = evaluate_regression(y_test_bt, bt_pred, model_cfg["name"])
            m["fold_id"] = i + 1
            m["fold_test_start"] = fold_start
            m["fold_test_end"] = fold_end - pd.Timedelta(hours=1)
            m["train_rows"] = len(train_df)
            m["test_rows"] = len(test_df)
            bt_metrics.append(m)

            temp_pred = test_df[["datetime", target_col]].copy()
            temp_pred.rename(columns={target_col: "真实值"}, inplace=True)
            temp_pred["预测值"] = bt_pred
            temp_pred["fold_id"] = i + 1
            temp_pred["绝对误差"] = np.abs(temp_pred["预测值"] - temp_pred["真实值"])
            bt_preds.append(temp_pred)
        except Exception as e:
            log_print(f"滚动回测 fold {i + 1} 失败：{e}")

    metrics_df = pd.DataFrame(bt_metrics)
    preds_df = pd.concat(bt_preds, axis=0, ignore_index=True) if len(bt_preds) > 0 else pd.DataFrame()

    return metrics_df, preds_df


def detect_anomalies(pred_result: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = pred_result.copy()
    df["预测误差"] = df["预测值"] - df["真实值"]
    df["绝对误差"] = np.abs(df["预测误差"])
    df["绝对百分比误差(%)"] = np.abs(df["预测误差"]) / np.where(np.abs(df["真实值"]) < 1e-6, 1e-6, np.abs(df["真实值"])) * 100

    abs_err_threshold = max(df["绝对误差"].quantile(0.95), ANOMALY_MIN_ABS_ERROR)
    residual_std = df["预测误差"].std(ddof=0)
    if residual_std < 1e-6:
        residual_std = 1e-6
    df["残差Z分数"] = (df["预测误差"] - df["预测误差"].mean()) / residual_std

    spike_threshold = df["真实值"].quantile(0.95)

    df["是否异常"] = (
        (df["绝对误差"] >= abs_err_threshold) |
        (np.abs(df["残差Z分数"]) >= 2.5)
    ).astype(int)
    df["是否尖峰价"] = (df["真实值"] >= spike_threshold).astype(int)
    df["是否高峰时段"] = df["datetime"].dt.hour.isin([6, 7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)

    anomaly_df = df[df["是否异常"] == 1].copy().sort_values("绝对误差", ascending=False)
    hourly_err = df.groupby(df["datetime"].dt.hour).agg(
        样本数=("真实值", "size"),
        MAE=("绝对误差", "mean"),
        RMSE=("预测误差", lambda x: float(np.sqrt(np.mean(np.square(x))))),
        平均真实价格=("真实值", "mean"),
        尖峰价占比=("是否尖峰价", "mean"),
        异常占比=("是否异常", "mean")
    ).reset_index().rename(columns={"datetime": "hour"}).rename(columns={"datetime": "小时"})

    return anomaly_df, hourly_err


# =========================
# 主流程开始
# =========================
log_print("=" * 80)
log_print("开始读取主表数据...")

if not os.path.exists(MASTER_FILE):
    raise FileNotFoundError(f"未找到主表文件：{MASTER_FILE}")

try:
    df = pd.read_excel(MASTER_FILE, engine="openpyxl")
except Exception:
    df = pd.read_excel(MASTER_FILE)

log_print(f"主表读取成功，数据形状：{df.shape}")
log_print(f"字段列表：{list(df.columns)}")

if "datetime" not in df.columns:
    raise ValueError("主表中未找到 datetime 字段，请检查文件结构。")

df["datetime"] = pd.to_datetime(df["datetime"])
df = df.sort_values("datetime").reset_index(drop=True)

# forecast_evaluated_at 若存在则转时间
if "forecast_evaluated_at" in df.columns:
    df["forecast_evaluated_at"] = pd.to_datetime(df["forecast_evaluated_at"], errors="coerce")

before_drop = len(df)
df = df.drop_duplicates(subset=["datetime"]).reset_index(drop=True)
after_drop = len(df)
log_print(f"按 datetime 去重后：{before_drop} -> {after_drop}")

# =========================
# 1. 数据质量检查
# =========================
log_print("=" * 80)
log_print("开始数据质量检查...")

quality_rows = []
for col in df.columns:
    quality_rows.append({
        "字段名": col,
        "数据类型": str(df[col].dtype),
        "缺失值数量": int(df[col].isna().sum()),
        "缺失率(%)": round(df[col].isna().mean() * 100, 6),
        "唯一值数量": int(df[col].nunique(dropna=True))
    })

quality_df = pd.DataFrame(quality_rows)
quality_df.to_excel(os.path.join(TABLE_DIR, "01_数据质量检查.xlsx"), index=False)

numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
desc_df = df[numeric_cols].describe().T
desc_df.to_excel(os.path.join(TABLE_DIR, "02_数值字段描述统计.xlsx"))

# =========================
# 2. 基础 EDA 图表
# =========================
log_print("=" * 80)
log_print("开始输出EDA图表...")

# 若主表已有这些列，也重新计算保证一致
df = create_time_features(df, dt_col="datetime")

# 2.1 电价时间序列图
fig = plt.figure(figsize=(16, 6))
plt.plot(df["datetime"], df["da_price"], linewidth=0.8)
plt.title("DOM区域日前电价时间序列图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "01_日前电价时间序列图.png"))

# 2.2 实际负荷时间序列图
if "actual_load" in df.columns:
    fig = plt.figure(figsize=(16, 6))
    plt.plot(df["datetime"], df["actual_load"], linewidth=0.8)
    plt.title("DOM区域实际负荷时间序列图")
    plt.xlabel("时间")
    plt.ylabel("实际负荷（MW）")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "02_实际负荷时间序列图.png"))

# 2.3 按小时平均电价
hourly_mean = df.groupby("hour", as_index=False)["da_price"].mean()
fig = plt.figure(figsize=(10, 5))
plt.plot(hourly_mean["hour"], hourly_mean["da_price"], marker="o", linewidth=1)
plt.title("按小时平均日前电价")
plt.xlabel("小时")
plt.ylabel("平均日前电价（USD/MWh）")
plt.xticks(range(24))
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "03_按小时平均日前电价.png"))

# 2.4 按星期平均电价
dow_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
dow_mean = df.groupby("day_of_week", as_index=False)["da_price"].mean()
dow_mean["星期"] = dow_mean["day_of_week"].map(dow_map)
fig = plt.figure(figsize=(10, 5))
plt.bar(dow_mean["星期"], dow_mean["da_price"])
plt.title("按星期平均日前电价")
plt.xlabel("星期")
plt.ylabel("平均日前电价（USD/MWh）")
plt.grid(alpha=0.3, axis="y")
save_fig(fig, os.path.join(FIG_DIR, "04_按星期平均日前电价.png"))

# 2.5 月均电价
monthly_mean = df.groupby(["year", "month"], as_index=False)["da_price"].mean()
monthly_mean["year_month"] = monthly_mean["year"].astype(str) + "-" + monthly_mean["month"].astype(str).str.zfill(2)
fig = plt.figure(figsize=(16, 6))
plt.plot(monthly_mean["year_month"], monthly_mean["da_price"], marker="o", linewidth=1)
plt.title("按月份平均日前电价")
plt.xlabel("月份")
plt.ylabel("平均日前电价（USD/MWh）")
plt.xticks(rotation=60)
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "05_按月份平均日前电价.png"))

# 2.6 峰谷价差（按天）
daily_peak_valley = df.groupby(df["datetime"].dt.date).agg(
    日峰值=("da_price", "max"),
    日谷值=("da_price", "min")
).reset_index()
daily_peak_valley["峰谷价差"] = daily_peak_valley["日峰值"] - daily_peak_valley["日谷值"]
fig = plt.figure(figsize=(16, 6))
plt.plot(pd.to_datetime(daily_peak_valley["datetime"]), daily_peak_valley["峰谷价差"], linewidth=0.8)
plt.title("日前电价日峰谷价差趋势图")
plt.xlabel("日期")
plt.ylabel("峰谷价差（USD/MWh）")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "06_日前电价日峰谷价差趋势图.png"))

# 2.7 电价与负荷关系散点图
if "actual_load" in df.columns:
    sample_df = df[["actual_load", "da_price"]].dropna()
    if len(sample_df) > 5000:
        sample_df = sample_df.sample(5000, random_state=RANDOM_STATE)
    fig = plt.figure(figsize=(8, 6))
    plt.scatter(sample_df["actual_load"], sample_df["da_price"], s=8, alpha=0.5)
    plt.title("实际负荷与日前电价关系散点图")
    plt.xlabel("实际负荷（MW）")
    plt.ylabel("日前电价（USD/MWh）")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "07_实际负荷与日前电价关系散点图.png"))

# 2.8 温度与电价关系散点图
if "temperature" in df.columns:
    sample_df = df[["temperature", "da_price"]].dropna()
    if len(sample_df) > 5000:
        sample_df = sample_df.sample(5000, random_state=RANDOM_STATE)
    fig = plt.figure(figsize=(8, 6))
    plt.scatter(sample_df["temperature"], sample_df["da_price"], s=8, alpha=0.5)
    plt.title("温度与日前电价关系散点图")
    plt.xlabel("温度（℃）")
    plt.ylabel("日前电价（USD/MWh）")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "08_温度与日前电价关系散点图.png"))

# 2.9 星期-小时热力图
pivot_table = df.pivot_table(values="da_price", index="day_of_week", columns="hour", aggfunc="mean")
fig = plt.figure(figsize=(12, 6))
plt.imshow(pivot_table, aspect="auto")
plt.colorbar(label="平均日前电价（USD/MWh）")
plt.title("星期-小时平均日前电价热力图")
plt.xlabel("小时")
plt.ylabel("星期（0=周一）")
plt.xticks(range(24))
plt.yticks(range(7))
save_fig(fig, os.path.join(FIG_DIR, "09_星期_小时平均日前电价热力图.png"))

# =========================
# 3. 特征工程
# =========================
log_print("=" * 80)
log_print("开始特征工程...")

df = add_business_features(df)
df = create_lag_features(df, target_col="da_price")
df = create_rolling_features(df)
df = create_ewm_features(df)
df = create_history_group_features(df)

target_col = "da_price"
feature_cols = build_feature_list(df)

model_df = df[["datetime", target_col] + feature_cols].copy()
model_df = model_df.dropna().reset_index(drop=True)

log_print(f"特征工程完成，建模数据形状：{model_df.shape}")
log_print(f"特征数量：{len(feature_cols)}")
model_df.to_excel(os.path.join(TABLE_DIR, "03_建模数据样本.xlsx"), index=False)
model_df.to_excel(os.path.join(TABLE_DIR, "09_特征工程后建模表.xlsx"), index=False)

# =========================
# 4. 时间切分：训练 / 验证 / 测试
# =========================
log_print("=" * 80)
log_print("开始时间序列切分...")

max_dt = model_df["datetime"].max()
test_start_dt = max_dt - pd.Timedelta(days=TEST_DAYS)
val_start_dt = test_start_dt - pd.Timedelta(days=VAL_DAYS)

train_df = model_df[model_df["datetime"] < val_start_dt].copy()
val_df = model_df[(model_df["datetime"] >= val_start_dt) & (model_df["datetime"] < test_start_dt)].copy()
test_df = model_df[model_df["datetime"] >= test_start_dt].copy()

X_train = train_df[feature_cols]
y_train = train_df[target_col]
X_val = val_df[feature_cols]
y_val = val_df[target_col]
X_test = test_df[feature_cols]
y_test = test_df[target_col]

log_print(f"训练集：{train_df.shape}")
log_print(f"验证集：{val_df.shape}")
log_print(f"测试集：{test_df.shape}")
log_print(f"验证集开始时间：{val_start_dt}")
log_print(f"测试集开始时间：{test_start_dt}")

# =========================
# 5. 基线模型与线性回归
# =========================
log_print("=" * 80)
log_print("开始训练基线模型...")

test_metrics_list = []

# 基线1：前24小时同小时
baseline_pred_24 = test_df["da_price_lag_24"].values
test_metrics_list.append(evaluate_regression(y_test, baseline_pred_24, "基线模型_前24小时同小时"))

# 基线2：上周同一时刻
if "da_price_lag_168" in test_df.columns:
    baseline_pred_168 = test_df["da_price_lag_168"].values
    test_metrics_list.append(evaluate_regression(y_test, baseline_pred_168, "基线模型_上周同时刻"))
else:
    baseline_pred_168 = np.repeat(np.nan, len(test_df))

# 线性回归
linear_model = LinearRegression()
linear_model.fit(pd.concat([X_train, X_val], axis=0), pd.concat([y_train, y_val], axis=0))
linear_pred = np.clip(linear_model.predict(X_test), a_min=0, a_max=None)
test_metrics_list.append(evaluate_regression(y_test, linear_pred, "线性回归"))

# =========================
# 6. 验证集模型选择 + 最优模型重训
# =========================
best_cfg, candidate_val_df = select_best_model_by_validation(X_train, y_train, X_val, y_val)
candidate_val_df.to_excel(os.path.join(TABLE_DIR, "04_候选模型验证集结果.xlsx"), index=False)
log_print(f"验证集最优模型：{best_cfg['name']}")

X_train_full = pd.concat([X_train, X_val], axis=0)
y_train_full = pd.concat([y_train, y_val], axis=0)

best_model, best_test_pred = fit_predict_with_config(best_cfg, X_train_full, y_train_full, X_test)
best_test_pred = np.clip(best_test_pred, a_min=0, a_max=None)
best_model_name = best_cfg["name"]

test_metrics_list.append(evaluate_regression(y_test, best_test_pred, best_model_name))

metrics_df = pd.DataFrame(test_metrics_list).sort_values(["RMSE", "MAE", "MAPE(%)"], ascending=[True, True, True]).reset_index(drop=True)
metrics_df.to_excel(os.path.join(TABLE_DIR, "05_模型评估结果.xlsx"), index=False)

log_print("=" * 80)
log_print("测试集模型评估结果：")
log_print(metrics_df.to_string(index=False))

# =========================
# 7. 测试集预测结果保存
# =========================
pred_result = test_df[["datetime", "da_price"]].copy()
pred_result.rename(columns={"da_price": "真实值"}, inplace=True)
pred_result["基线_前24小时同小时"] = baseline_pred_24
if np.isfinite(baseline_pred_168).any():
    pred_result["基线_上周同一时刻"] = baseline_pred_168
pred_result["线性回归预测值"] = linear_pred
pred_result["预测值"] = best_test_pred
pred_result["模型"] = best_model_name
pred_result["预测误差"] = pred_result["预测值"] - pred_result["真实值"]
pred_result["绝对误差"] = np.abs(pred_result["预测误差"])
pred_result["绝对百分比误差(%)"] = np.abs(pred_result["预测误差"]) / np.where(np.abs(pred_result["真实值"]) < 1e-6, 1e-6, np.abs(pred_result["真实值"])) * 100
pred_result.to_excel(os.path.join(TABLE_DIR, "06_测试集预测结果.xlsx"), index=False)

# =========================
# 8. 预测结果图
# =========================
log_print("=" * 80)
log_print("开始输出预测结果图...")

# 8.1 测试集整体真实值 vs 预测值
fig = plt.figure(figsize=(16, 6))
plt.plot(pred_result["datetime"], pred_result["真实值"], label="真实值", linewidth=1)
plt.plot(pred_result["datetime"], pred_result["预测值"], label=f"{best_model_name}预测值", linewidth=1)
plt.title(f"测试集真实值与{best_model_name}预测值对比图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.legend()
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "10_测试集真实值与主模型预测值对比图.png"))

# 8.2 最后7天局部预测图
last_7d = pred_result[pred_result["datetime"] >= pred_result["datetime"].max() - pd.Timedelta(days=7)].copy()
fig = plt.figure(figsize=(16, 6))
plt.plot(last_7d["datetime"], last_7d["真实值"], label="真实值", linewidth=1.2)
plt.plot(last_7d["datetime"], last_7d["预测值"], label=f"{best_model_name}预测值", linewidth=1.2)
plt.title("最后7天真实值与主模型预测值局部对比图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.legend()
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "11_最后7天局部预测对比图.png"))

# 8.3 误差时间序列图
fig = plt.figure(figsize=(16, 6))
plt.plot(pred_result["datetime"], pred_result["预测误差"], linewidth=0.8)
plt.axhline(0, linestyle="--", linewidth=1)
plt.title(f"{best_model_name}预测误差时间序列图")
plt.xlabel("时间")
plt.ylabel("预测误差")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "12_主模型预测误差时间序列图.png"))

# 8.4 绝对误差分布图
fig = plt.figure(figsize=(10, 6))
plt.hist(pred_result["绝对误差"], bins=50)
plt.title(f"{best_model_name}绝对误差分布图")
plt.xlabel("绝对误差")
plt.ylabel("频数")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "13_主模型绝对误差分布图.png"))

# 8.5 分小时MAE图
hourly_mae_df = pred_result.copy()
hourly_mae_df["hour"] = hourly_mae_df["datetime"].dt.hour
hourly_mae = hourly_mae_df.groupby("hour", as_index=False)["绝对误差"].mean()
fig = plt.figure(figsize=(10, 5))
plt.bar(hourly_mae["hour"], hourly_mae["绝对误差"])
plt.title("测试集按小时平均绝对误差（MAE）")
plt.xlabel("小时")
plt.ylabel("平均绝对误差")
plt.xticks(range(24))
plt.grid(alpha=0.3, axis="y")
save_fig(fig, os.path.join(FIG_DIR, "14_测试集按小时平均绝对误差图.png"))

# =========================
# 9. 特征重要性
# =========================
log_print("=" * 80)
log_print("开始输出特征重要性...")

feature_importance_df = get_feature_importance(best_model, feature_cols)
feature_importance_df.to_excel(os.path.join(TABLE_DIR, "07_特征重要性.xlsx"), index=False)

if not feature_importance_df.empty:
    top_n = min(TOP_N_FEATURES, len(feature_importance_df))
    top_df = feature_importance_df.head(top_n).iloc[::-1]
    fig = plt.figure(figsize=(10, 10))
    plt.barh(top_df["特征"], top_df["重要性"])
    plt.title(f"{best_model_name}前{top_n}个特征重要性")
    plt.xlabel("重要性")
    plt.ylabel("特征")
    plt.grid(alpha=0.3, axis="x")
    save_fig(fig, os.path.join(FIG_DIR, "15_主模型特征重要性图.png"))

# =========================
# 10. 异常波动识别
# =========================
log_print("=" * 80)
log_print("开始异常波动识别...")

anomaly_df, hourly_error_df = detect_anomalies(pred_result)
anomaly_df.to_excel(os.path.join(TABLE_DIR, "08_异常波动明细.xlsx"), index=False)
hourly_error_df.to_excel(os.path.join(TABLE_DIR, "09_按小时误差统计.xlsx"), index=False)

# 10.1 异常点时间序列图
fig = plt.figure(figsize=(16, 6))
plt.plot(pred_result["datetime"], pred_result["真实值"], label="真实值", linewidth=1)
plt.plot(pred_result["datetime"], pred_result["预测值"], label="预测值", linewidth=1)
if not anomaly_df.empty:
    plt.scatter(anomaly_df["datetime"], anomaly_df["真实值"], s=25, label="异常点", alpha=0.8)
plt.title("测试集异常波动识别图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.legend()
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "16_测试集异常波动识别图.png"))

# 10.2 Top异常点柱状图
if not anomaly_df.empty:
    top_anomaly = anomaly_df.head(20).copy()
    top_anomaly["标签"] = top_anomaly["datetime"].dt.strftime("%m-%d %H:%M")
    fig = plt.figure(figsize=(12, 8))
    plt.barh(top_anomaly["标签"].iloc[::-1], top_anomaly["绝对误差"].iloc[::-1])
    plt.title("Top20异常波动时点绝对误差")
    plt.xlabel("绝对误差")
    plt.ylabel("时点")
    plt.grid(alpha=0.3, axis="x")
    save_fig(fig, os.path.join(FIG_DIR, "17_Top20异常波动时点绝对误差图.png"))

# =========================
# 11. 滚动回测
# =========================
rolling_metrics_df, rolling_preds_df = rolling_backtest(
    model_cfg=best_cfg,
    model_df=model_df,
    feature_cols=feature_cols,
    target_col=target_col,
    fold_days=ROLLING_BACKTEST_FOLD_DAYS,
    n_folds=ROLLING_BACKTEST_FOLDS,
    min_train_days=MIN_TRAIN_DAYS_FOR_BACKTEST
)

if not rolling_metrics_df.empty:
    rolling_metrics_df.to_excel(os.path.join(TABLE_DIR, "10_滚动回测结果.xlsx"), index=False)
else:
    pd.DataFrame().to_excel(os.path.join(TABLE_DIR, "10_滚动回测结果.xlsx"), index=False)

if not rolling_preds_df.empty:
    rolling_preds_df.to_excel(os.path.join(TABLE_DIR, "11_滚动回测预测明细.xlsx"), index=False)

# 11.1 滚动回测RMSE图
if not rolling_metrics_df.empty:
    fig = plt.figure(figsize=(10, 5))
    plt.plot(rolling_metrics_df["fold_id"], rolling_metrics_df["RMSE"], marker="o", linewidth=1)
    plt.title("滚动回测各Fold的RMSE变化")
    plt.xlabel("Fold")
    plt.ylabel("RMSE")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "18_滚动回测RMSE变化图.png"))

    fig = plt.figure(figsize=(10, 5))
    plt.plot(rolling_metrics_df["fold_id"], rolling_metrics_df["MAPE(%)"], marker="o", linewidth=1)
    plt.title("滚动回测各Fold的MAPE变化")
    plt.xlabel("Fold")
    plt.ylabel("MAPE(%)")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "19_滚动回测MAPE变化图.png"))

# =========================
# 12. 未来24小时预测（演示版，保留原核心功能）
# =========================
log_print("=" * 80)
log_print("开始生成未来24小时预测结果（演示版）...")

future_24 = model_df.tail(24).copy()
future_24_X = future_24[feature_cols].copy()
future_24_pred = np.clip(best_model.predict(future_24_X), a_min=0, a_max=None)

future_24_result = future_24[["datetime"]].copy()
future_24_result["预测的未来24小时日前电价"] = future_24_pred
future_24_result.to_excel(os.path.join(TABLE_DIR, "12_未来24小时预测结果_演示版.xlsx"), index=False)

fig = plt.figure(figsize=(12, 6))
plt.plot(future_24_result["datetime"], future_24_result["预测的未来24小时日前电价"], marker="o", linewidth=1)
plt.title("未来24小时日前电价预测结果（演示版）")
plt.xlabel("时间")
plt.ylabel("预测电价（USD/MWh）")
plt.xticks(rotation=45)
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "20_未来24小时日前电价预测图_演示版.png"))

# =========================
# 13. 业务统计摘要
# =========================
log_print("=" * 80)
log_print("开始输出业务统计结果...")

business_summary = []
business_summary.append({"指标": "样本总量", "值": len(df)})
business_summary.append({"指标": "起始时间", "值": str(df["datetime"].min())})
business_summary.append({"指标": "结束时间", "值": str(df["datetime"].max())})
business_summary.append({"指标": "平均日前电价", "值": round(df["da_price"].mean(), 4)})
business_summary.append({"指标": "日前电价最大值", "值": round(df["da_price"].max(), 4)})
business_summary.append({"指标": "日前电价最小值", "值": round(df["da_price"].min(), 4)})

if "actual_load" in df.columns:
    business_summary.append({"指标": "平均实际负荷", "值": round(df["actual_load"].mean(), 4)})
    business_summary.append({"指标": "最大实际负荷", "值": round(df["actual_load"].max(), 4)})

if "forecast_load" in df.columns:
    business_summary.append({"指标": "平均预测负荷", "值": round(df["forecast_load"].mean(), 4)})

if "temperature" in df.columns:
    business_summary.append({"指标": "平均温度", "值": round(df["temperature"].mean(), 4)})

business_summary.append({"指标": "测试集主模型", "值": best_model_name})
main_metric_row = metrics_df[metrics_df["模型"] == best_model_name]
if not main_metric_row.empty:
    business_summary.append({"指标": "测试集MAE", "值": round(float(main_metric_row.iloc[0]["MAE"]), 6)})
    business_summary.append({"指标": "测试集RMSE", "值": round(float(main_metric_row.iloc[0]["RMSE"]), 6)})
    business_summary.append({"指标": "测试集MAPE(%)", "值": round(float(main_metric_row.iloc[0]["MAPE(%)"]), 6)})
    business_summary.append({"指标": "测试集R2", "值": round(float(main_metric_row.iloc[0]["R2"]), 6)})

business_summary.append({"指标": "异常点数量", "值": int(len(anomaly_df))})
business_summary.append({"指标": "测试集异常点占比(%)", "值": round(len(anomaly_df) / max(len(pred_result), 1) * 100, 6)})

business_summary_df = pd.DataFrame(business_summary)
business_summary_df.to_excel(os.path.join(TABLE_DIR, "13_业务统计摘要.xlsx"), index=False)

# =========================
# 14. 结果说明文件
# =========================
readme_text = f"""
项目运行完成。

一、输入文件
- 主表路径：{MASTER_FILE}

二、输出目录
- 图表目录：{FIG_DIR}
- 结果表目录：{TABLE_DIR}
- 日志目录：{LOG_DIR}

三、核心优化内容
1. 在保留原有数据读取、EDA、特征工程、模型评估、图表输出、未来24小时演示预测功能基础上，新增：
   - 验证集候选模型选择
   - 更丰富的时序特征
   - 异常波动识别
   - 滚动回测
2. 主模型不再固定写死为某一个模型，而是先在验证集比较，再在训练+验证集重训后用于测试集预测。

四、本次最终主模型
- 使用模型：{best_model_name}

五、主要输出文件
1. 01_数据质量检查.xlsx
2. 02_数值字段描述统计.xlsx
3. 03_建模数据样本.xlsx
4. 04_候选模型验证集结果.xlsx
5. 05_模型评估结果.xlsx
6. 06_测试集预测结果.xlsx
7. 07_特征重要性.xlsx
8. 08_异常波动明细.xlsx
9. 09_按小时误差统计.xlsx
10. 10_滚动回测结果.xlsx
11. 11_滚动回测预测明细.xlsx
12. 12_未来24小时预测结果_演示版.xlsx
13. 13_业务统计摘要.xlsx

六、当前阶段说明
- 当前已完成：EDA分析 + 特征工程 + 首版/优化版预测建模 + 异常波动识别 + 滚动回测
- 下一步建议：
  1）接入真实未来24小时天气预报数据
  2）接入更严格的未来负荷预测口径
  3）针对尖峰价时段增加分类辅助任务（是否尖峰价）
  4）增加AI自动解读日报模块
"""

with open(os.path.join(RESULT_DIR, "README_结果说明.txt"), "w", encoding="utf-8") as f:
    f.write(readme_text)

log_print("=" * 80)
log_print("全部运行完成！")
log_print(f"图表输出目录：{FIG_DIR}")
log_print(f"结果表输出目录：{TABLE_DIR}")
log_print(f"日志输出目录：{LOG_DIR}")
log_print(f"最终主模型：{best_model_name}")
