# -*- coding: utf-8 -*-
"""
项目名称：基于公开电力市场数据的电价预测与智能分析系统
当前版本：高峰尖刺增强版（严格去泄漏 + 高峰/尖刺专项优化）

版本说明：
1）保留原有核心功能：数据读取、数据质量检查、EDA、特征工程、模型评估、测试集预测、异常识别、滚动回测、未来24小时正式前瞻预测输出；
2）继续保持严格去泄漏口径：不使用当前时点 da_price 分解项、rt 市场后验信息、actual_load 当前值、当前时点实况天气等未来不可得变量；
3）新增高峰尖刺精度增强：
   - 增加高峰/晨峰/晚峰专用安全特征；
   - 候选模型选择时，不只看整体 RMSE，也联合考察高峰时段与尖峰样本表现；
   - 新增“高峰尖刺专项模型”与“尖峰风险分类器”；
   - 通过验证集自动搜索融合强度 alpha，在尽量不破坏整体精度的前提下，提升高峰尖刺时段拟合能力；
4）新增专项结果输出：
   - 高峰增强验证结果
   - 高峰/尖刺专项评估
   - 高峰时段对比图
5）全部结果继续保存到你指定路径。
"""

import os
import math
import warnings
from typing import List, Dict, Tuple, Optional

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import requests
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_fscore_support,
    r2_score,
    roc_auc_score,
)
from sklearn.ensemble import (
    ExtraTreesRegressor,
    RandomForestRegressor,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    HistGradientBoostingClassifier,
)
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import ElasticNet, HuberRegressor, LinearRegression, LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# =========================
# 路径配置
# =========================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "output")
RESULT_DIR = os.path.join(PROJECT_ROOT, "结果-3")
MASTER_FILE = os.path.join(DATA_DIR, "master_table.xlsx")
FORECAST_LOAD_SELECTED_FILE = os.path.join(DATA_DIR, "forecast_load_selected.xlsx")

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
ANOMALY_MIN_ABS_ERROR = 30.0
TOP_N_FEATURES = 25
TARGET_COL = "da_price"
MORNING_PEAK_HOURS = [6, 7, 8, 9]
EVENING_PEAK_HOURS = [18, 19, 20, 21]
PEAK_HOURS = sorted(list(set(MORNING_PEAK_HOURS + EVENING_PEAK_HOURS + [10, 11])))
BLEND_ALPHA_GRID = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
PEAK_FLOOR_GRID = [0.0, 0.15, 0.25, 0.35]
SPIKE_THRESHOLD_GRID = np.round(np.arange(0.10, 0.81, 0.05), 2)
FORMAL_FORECAST_HOURS = 24
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_FORECAST_LAT = 37.5407
WEATHER_FORECAST_LON = -77.4360
WEATHER_TIMEZONE_NAME = "America/New_York"
ENABLE_ROLLING_BACKTEST = os.environ.get("ENABLE_ROLLING_BACKTEST", "1") != "0"

# 严格禁用的当前时点后验/泄漏字段
LEAKAGE_BANNED_RAW_COLS = [
    "da_price",
    "da_congestion_price",
    "da_marginal_loss_price",
    "da_system_energy_price",
    "rt_price",
    "rt_congestion_price",
    "rt_marginal_loss_price",
    "rt_system_energy_price",
    "price_spread_rt_minus_da",
    "actual_load",
    "load_gap",
    "load_ratio",
    "temperature",
    "wind_speed",
    "precipitation",
]

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
        "R2": r2,
    }


def subset_metrics(y_true, y_pred, name: str) -> Dict:
    if len(y_true) == 0:
        return {"模型": name, "MAE": np.nan, "RMSE": np.nan, "MAPE(%)": np.nan, "R2": np.nan}
    return evaluate_regression(y_true, y_pred, name)


def expanding_group_mean(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding().mean()


def expanding_group_std(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding().std()


def shifted_group_rolling(series: pd.Series, window: int, agg: str, quantile: float | None = None) -> pd.Series:
    shifted = series.shift(1)
    rolling = shifted.rolling(window=window, min_periods=max(3, min(window, 24)))
    if agg == "mean":
        return rolling.mean()
    if agg == "median":
        return rolling.median()
    if agg == "std":
        return rolling.std()
    if agg == "quantile":
        return rolling.quantile(float(quantile or 0.5))
    raise ValueError(f"不支持的 rolling 聚合：{agg}")


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


def try_import_lightgbm_classifier():
    try:
        from lightgbm import LGBMClassifier
        return LGBMClassifier
    except Exception:
        return None


def try_import_catboost_regressor():
    try:
        from catboost import CatBoostRegressor
        return CatBoostRegressor
    except Exception:
        return None


def try_import_catboost_classifier():
    try:
        from catboost import CatBoostClassifier
        return CatBoostClassifier
    except Exception:
        return None


def fit_model_with_optional_weight(model, X, y, sample_weight=None):
    if sample_weight is None:
        model.fit(X, y)
        return model
    try:
        model.fit(X, y, sample_weight=sample_weight)
    except (TypeError, ValueError) as exc:
        if "sample_weight" not in str(exc):
            raise
        model.fit(X, y)
    return model


# =========================
# 特征工程
# =========================
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

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["doy_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)
    return df


def create_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lag_features = {
        TARGET_COL: [1, 2, 3, 6, 12, 18, 24, 25, 48, 72, 96, 168, 169],
        "forecast_load": [1, 2, 3, 24, 25, 48, 168],
        "actual_load": [1, 2, 24, 25, 48, 168],
        "temperature": [1, 2, 24, 48, 168],
        "wind_speed": [1, 24, 48],
        "precipitation": [1, 24, 48],
        "price_spread_rt_minus_da": [1, 24, 168],
    }
    for col, lags in lag_features.items():
        if col in df.columns:
            for lag in lags:
                df[f"{col}_lag_{lag}"] = df[col].shift(lag)
    return df


def create_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rolling_config = {
        TARGET_COL: [6, 12, 24, 48, 168],
        "forecast_load": [24, 48, 168],
        "actual_load": [24, 48, 168],
        "temperature": [24, 48, 168],
        "wind_speed": [24, 48],
        "precipitation": [24, 48],
    }
    for col, windows in rolling_config.items():
        if col in df.columns:
            shifted = df[col].shift(1)
            for w in windows:
                df[f"{col}_roll_mean_{w}"] = shifted.rolling(window=w).mean()
                df[f"{col}_roll_std_{w}"] = shifted.rolling(window=w).std()
                df[f"{col}_roll_min_{w}"] = shifted.rolling(window=w).min()
                df[f"{col}_roll_max_{w}"] = shifted.rolling(window=w).max()
                df[f"{col}_roll_median_{w}"] = shifted.rolling(window=w).median()
    return df


def create_ewm_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    ewm_config = {
        TARGET_COL: [6, 24, 168],
        "forecast_load": [24, 168],
        "actual_load": [24, 168],
        "temperature": [24, 168],
    }
    for col, spans in ewm_config.items():
        if col in df.columns:
            shifted = df[col].shift(1)
            for span in spans:
                df[f"{col}_ewm_mean_{span}"] = shifted.ewm(span=span, adjust=False).mean()
                df[f"{col}_ewm_std_{span}"] = shifted.ewm(span=span, adjust=False).std()
    return df


def create_history_group_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if TARGET_COL in df.columns:
        if "hour" in df.columns:
            df["da_price_hist_hour_mean"] = df.groupby("hour")[TARGET_COL].transform(expanding_group_mean)
            df["da_price_hist_hour_std"] = df.groupby("hour")[TARGET_COL].transform(expanding_group_std)
            df["same_hour_price_mean_7d"] = df.groupby("hour")[TARGET_COL].transform(lambda s: shifted_group_rolling(s, 7, "mean"))
            df["same_hour_price_median_14d"] = df.groupby("hour")[TARGET_COL].transform(lambda s: shifted_group_rolling(s, 14, "median"))
            df["same_hour_price_p75_30d"] = df.groupby("hour")[TARGET_COL].transform(lambda s: shifted_group_rolling(s, 30, "quantile", 0.75))
            df["same_hour_price_p90_30d"] = df.groupby("hour")[TARGET_COL].transform(lambda s: shifted_group_rolling(s, 30, "quantile", 0.90))
            df["same_hour_price_std_30d"] = df.groupby("hour")[TARGET_COL].transform(lambda s: shifted_group_rolling(s, 30, "std"))
        if "day_of_week" in df.columns:
            df["da_price_hist_dow_mean"] = df.groupby("day_of_week")[TARGET_COL].transform(expanding_group_mean)
        if "month" in df.columns:
            df["da_price_hist_month_mean"] = df.groupby("month")[TARGET_COL].transform(expanding_group_mean)
        if "is_weekend" in df.columns:
            df["da_price_hist_weekend_mean"] = df.groupby("is_weekend")[TARGET_COL].transform(expanding_group_mean)
    return df


def add_safe_business_features(df: pd.DataFrame) -> pd.DataFrame:
    """仅构造严格不泄漏的业务特征。"""
    df = df.copy()

    # 天气相关：只基于滞后天气构造，不使用当前时点实况天气
    if "temperature_lag_1" in df.columns:
        df["temperature_lag_1_sq"] = df["temperature_lag_1"] ** 2
        df["cooling_degree_lag_1"] = np.maximum(df["temperature_lag_1"] - 22, 0)
        df["heating_degree_lag_1"] = np.maximum(18 - df["temperature_lag_1"], 0)
    if "temperature_lag_24" in df.columns and "temperature_lag_48" in df.columns:
        df["temp_hist_change_24h"] = df["temperature_lag_24"] - df["temperature_lag_48"]
    if "temperature_lag_1" in df.columns and "temperature_lag_2" in df.columns:
        df["temp_hist_change_1h"] = df["temperature_lag_1"] - df["temperature_lag_2"]
    if "temperature_lag_1" in df.columns:
        temp_mean_7d = df["temperature_lag_1"].shift(1).rolling(window=168, min_periods=24).mean()
        df["temperature_deviation_from_7d_mean"] = df["temperature_lag_1"] - temp_mean_7d
        df["heating_degree_hour"] = np.maximum(18 - df["temperature_lag_1"], 0)
        df["cooling_degree_hour"] = np.maximum(df["temperature_lag_1"] - 22, 0)
        low_q = df["temperature_lag_1"].shift(1).rolling(window=168, min_periods=24).quantile(0.10)
        high_q = df["temperature_lag_1"].shift(1).rolling(window=168, min_periods=24).quantile(0.90)
        df["extreme_temp_flag"] = ((df["temperature_lag_1"] <= low_q) | (df["temperature_lag_1"] >= high_q)).astype(int)

    # 负荷相关：forecast_load_t 可用；actual_load_t 不可用，只允许其滞后值
    if "forecast_load" in df.columns:
        if "forecast_load_lag_1" in df.columns:
            df["forecast_load_change_1h_safe"] = df["forecast_load"] - df["forecast_load_lag_1"]
            df["forecast_load_diff_1h"] = df["forecast_load_change_1h_safe"]
        if "forecast_load_lag_24" in df.columns:
            df["forecast_load_change_24h_safe"] = df["forecast_load"] - df["forecast_load_lag_24"]
            df["forecast_load_diff_24h"] = df["forecast_load_change_24h_safe"]
        if "forecast_load_lag_3" in df.columns:
            df["forecast_load_diff_3h"] = df["forecast_load"] - df["forecast_load_lag_3"]
        if "forecast_load_lag_24" in df.columns:
            df["forecast_vs_hist24_ratio"] = df["forecast_load"] / np.where(np.abs(df["forecast_load_lag_24"]) < 1e-6, 1e-6, np.abs(df["forecast_load_lag_24"]))
        if "forecast_load_diff_1h" in df.columns:
            df["forecast_load_ramp_rate"] = df["forecast_load_diff_1h"] / np.where(np.abs(df["forecast_load_lag_1"]) < 1e-6, 1e-6, np.abs(df["forecast_load_lag_1"]))
    if "actual_load_lag_1" in df.columns and "actual_load_lag_2" in df.columns:
        df["actual_load_hist_change_1h"] = df["actual_load_lag_1"] - df["actual_load_lag_2"]
    if "actual_load_lag_24" in df.columns and "actual_load_lag_48" in df.columns:
        df["actual_load_hist_change_24h"] = df["actual_load_lag_24"] - df["actual_load_lag_48"]

    # 价格相关：只允许基于滞后值构造历史变化，不允许把当前 da_price 直接揉进特征
    if "da_price_lag_1" in df.columns and "da_price_lag_2" in df.columns:
        df["price_hist_change_1h"] = df["da_price_lag_1"] - df["da_price_lag_2"]
        df["price_hist_ratio_1h"] = df["da_price_lag_1"] / np.where(np.abs(df["da_price_lag_2"]) < 1e-6, 1e-6, np.abs(df["da_price_lag_2"]))
    if "da_price_lag_24" in df.columns and "da_price_lag_48" in df.columns:
        df["price_hist_change_24h"] = df["da_price_lag_24"] - df["da_price_lag_48"]
        df["price_hist_ratio_24h"] = df["da_price_lag_24"] / np.where(np.abs(df["da_price_lag_48"]) < 1e-6, 1e-6, np.abs(df["da_price_lag_48"]))
    if "da_price_lag_1" in df.columns and "da_price_lag_24" in df.columns:
        df["price_hist_gap_vs_yesterday_same_hour"] = df["da_price_lag_1"] - df["da_price_lag_24"]

    # 预测发布时间领先小时（可用）
    if "forecast_evaluated_at" in df.columns and "datetime" in df.columns:
        try:
            df["forecast_issue_lead_hours"] = (
                (pd.to_datetime(df["datetime"]) - pd.to_datetime(df["forecast_evaluated_at"]))
                .dt.total_seconds() / 3600.0
            )
        except Exception:
            pass

    # 峰谷时段标识
    if "hour" in df.columns:
        df["is_morning_peak"] = df["hour"].isin(MORNING_PEAK_HOURS).astype(int)
        df["is_evening_peak"] = df["hour"].isin(EVENING_PEAK_HOURS).astype(int)
        df["is_peak_hour"] = df["hour"].isin(PEAK_HOURS).astype(int)
        df["is_valley_hour"] = df["hour"].isin([0, 1, 2, 3, 4, 5]).astype(int)
        df["is_transition_hour"] = df["hour"].isin([5, 6, 7, 17, 18, 19]).astype(int)

    # 高峰专用安全交互特征
    if "forecast_load" in df.columns and "is_peak_hour" in df.columns:
        df["forecast_load_x_peak"] = df["forecast_load"] * df["is_peak_hour"]
    if "forecast_load_change_1h_safe" in df.columns and "is_peak_hour" in df.columns:
        df["forecast_load_change_1h_x_peak"] = df["forecast_load_change_1h_safe"] * df["is_peak_hour"]
    if "forecast_load_change_24h_safe" in df.columns and "is_peak_hour" in df.columns:
        df["forecast_load_change_24h_x_peak"] = df["forecast_load_change_24h_safe"] * df["is_peak_hour"]
    if "forecast_load" in df.columns and "is_evening_peak" in df.columns:
        df["is_evening_peak_x_forecast_load"] = df["is_evening_peak"] * df["forecast_load"]
    if "forecast_load" in df.columns and "is_morning_peak" in df.columns:
        df["is_morning_peak_x_forecast_load"] = df["is_morning_peak"] * df["forecast_load"]
    if "temperature_lag_1" in df.columns and "is_peak_hour" in df.columns:
        df["is_peak_hour_x_temperature"] = df["is_peak_hour"] * df["temperature_lag_1"]
    if "same_hour_price_p90_30d" in df.columns and "is_peak_hour" in df.columns:
        df["is_peak_hour_x_same_hour_price_p90"] = df["is_peak_hour"] * df["same_hour_price_p90_30d"]
    if "da_price_lag_1" in df.columns and "is_peak_hour" in df.columns:
        df["da_price_lag_1_x_peak"] = df["da_price_lag_1"] * df["is_peak_hour"]
    if "da_price_roll_mean_6" in df.columns and "is_peak_hour" in df.columns:
        df["da_price_roll_mean_6_x_peak"] = df["da_price_roll_mean_6"] * df["is_peak_hour"]
    if "da_price_hist_hour_mean" in df.columns and "is_peak_hour" in df.columns:
        df["da_price_hist_hour_mean_x_peak"] = df["da_price_hist_hour_mean"] * df["is_peak_hour"]
    if "price_hist_change_1h" in df.columns and "is_peak_hour" in df.columns:
        df["price_hist_change_1h_x_peak"] = df["price_hist_change_1h"] * df["is_peak_hour"]
    if "price_hist_gap_vs_yesterday_same_hour" in df.columns and "is_peak_hour" in df.columns:
        df["price_gap_yesterday_x_peak"] = df["price_hist_gap_vs_yesterday_same_hour"] * df["is_peak_hour"]

    # 风险代理：只基于历史和可用前瞻量
    if "da_price_roll_max_24" in df.columns and "da_price_lag_1" in df.columns:
        df["recent_price_tightness"] = df["da_price_lag_1"] / np.where(np.abs(df["da_price_roll_max_24"]) < 1e-6, 1e-6, np.abs(df["da_price_roll_max_24"]))
    if "da_price_hist_hour_mean" in df.columns and "da_price_lag_1" in df.columns:
        df["hourly_pressure_proxy"] = df["da_price_lag_1"] - df["da_price_hist_hour_mean"]

    # 误差记忆类特征：训练主表无外部误差记忆时使用安全零值占位，确保快速预测和训练 schema 一致。
    for col in ["hour_bias_mean", "scenario_mae", "historical_under_predict_rate"]:
        if col not in df.columns:
            df[col] = 0.0

    return df


def leakage_check_report(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in df.columns:
        risk_level = "低"
        reason = ""
        banned = False

        if col in LEAKAGE_BANNED_RAW_COLS:
            risk_level = "高"
            banned = True
            reason = "属于目标分解项、后验变量或当前时点不可用变量"
        elif col.startswith("price_change_") or col.startswith("price_ratio_"):
            risk_level = "高"
            banned = True
            reason = "旧版价格变化特征疑似直接使用当前时点 da_price 构造"
        elif col in ["load_gap", "load_ratio"]:
            risk_level = "高"
            banned = True
            reason = "依赖当前时点 actual_load，未来预测不可用"
        elif col in ["temperature", "wind_speed", "precipitation"]:
            risk_level = "中"
            banned = True
            reason = "当前时点观测天气在真实未来24小时预测中通常不可直接获得，需用天气预报替代"
        elif col.startswith("rt_") or col == "price_spread_rt_minus_da":
            risk_level = "高"
            banned = True
            reason = "依赖实时市场后验信息，未来日前预测不可用"

        rows.append({
            "字段名": col,
            "泄漏风险等级": risk_level,
            "是否禁用": int(banned),
            "说明": reason,
        })
    return pd.DataFrame(rows)


def build_feature_list(df: pd.DataFrame) -> List[str]:
    candidate_features = [
        # 时间特征
        "hour", "day_of_week", "month", "day", "year", "day_of_year", "week_of_year",
        "is_weekend", "is_month_start", "is_month_end",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos", "doy_sin", "doy_cos",

        # 可用业务特征
        "forecast_load", "forecast_issue_lead_hours",
        "is_peak_hour", "is_valley_hour", "is_morning_peak", "is_evening_peak", "is_transition_hour",
        "forecast_load_change_1h_safe", "forecast_load_change_24h_safe", "forecast_vs_hist24_ratio",
        "forecast_load_diff_1h", "forecast_load_diff_3h", "forecast_load_diff_24h", "forecast_load_ramp_rate",
        "forecast_load_x_peak", "forecast_load_change_1h_x_peak", "forecast_load_change_24h_x_peak",
        "is_evening_peak_x_forecast_load", "is_morning_peak_x_forecast_load",

        # 历史统计特征
        "da_price_hist_hour_mean", "da_price_hist_hour_std",
        "da_price_hist_dow_mean", "da_price_hist_month_mean", "da_price_hist_weekend_mean",
        "same_hour_price_mean_7d", "same_hour_price_median_14d", "same_hour_price_p75_30d",
        "same_hour_price_p90_30d", "same_hour_price_std_30d",

        # 历史价格滞后
        "da_price_lag_1", "da_price_lag_2", "da_price_lag_3", "da_price_lag_6", "da_price_lag_12",
        "da_price_lag_18", "da_price_lag_24", "da_price_lag_25", "da_price_lag_48",
        "da_price_lag_72", "da_price_lag_96", "da_price_lag_168", "da_price_lag_169",

        # 严格历史价格变化特征
        "price_hist_change_1h", "price_hist_change_24h", "price_hist_ratio_1h", "price_hist_ratio_24h",
        "price_spread_rt_minus_da_lag_1", "price_spread_rt_minus_da_lag_24", "price_spread_rt_minus_da_lag_168",
        "price_hist_gap_vs_yesterday_same_hour", "price_hist_change_1h_x_peak", "price_gap_yesterday_x_peak",
        "da_price_lag_1_x_peak", "da_price_roll_mean_6_x_peak", "da_price_hist_hour_mean_x_peak",
        "recent_price_tightness", "hourly_pressure_proxy",

        # 负荷滞后
        "forecast_load_lag_1", "forecast_load_lag_2", "forecast_load_lag_24",
        "forecast_load_lag_25", "forecast_load_lag_48", "forecast_load_lag_168",
        "actual_load_lag_1", "actual_load_lag_2", "actual_load_lag_24",
        "actual_load_lag_25", "actual_load_lag_48", "actual_load_lag_168",
        "actual_load_hist_change_1h", "actual_load_hist_change_24h",

        # 天气滞后
        "temperature_lag_1", "temperature_lag_2", "temperature_lag_24", "temperature_lag_48", "temperature_lag_168",
        "wind_speed_lag_1", "wind_speed_lag_24", "wind_speed_lag_48",
        "precipitation_lag_1", "precipitation_lag_24", "precipitation_lag_48",
        "temperature_lag_1_sq", "cooling_degree_lag_1", "heating_degree_lag_1",
        "temperature_deviation_from_7d_mean", "heating_degree_hour", "cooling_degree_hour", "extreme_temp_flag",
        "temp_hist_change_1h", "temp_hist_change_24h",
        "is_peak_hour_x_temperature", "is_peak_hour_x_same_hour_price_p90",

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
        "wind_speed_roll_mean_24", "wind_speed_roll_std_24",
        "precipitation_roll_mean_24", "precipitation_roll_std_24",

        # EWM
        "da_price_ewm_mean_6", "da_price_ewm_std_6",
        "da_price_ewm_mean_24", "da_price_ewm_std_24",
        "da_price_ewm_mean_168", "da_price_ewm_std_168",
        "forecast_load_ewm_mean_24", "forecast_load_ewm_std_24",
        "forecast_load_ewm_mean_168", "forecast_load_ewm_std_168",
        "actual_load_ewm_mean_24", "actual_load_ewm_std_24",
        "actual_load_ewm_mean_168", "actual_load_ewm_std_168",
        "temperature_ewm_mean_24", "temperature_ewm_std_24",
        "temperature_ewm_mean_168", "temperature_ewm_std_168",

        # 误差记忆占位/扩展特征
        "hour_bias_mean", "scenario_mae", "historical_under_predict_rate",
    ]
    return [f for f in candidate_features if f in df.columns]


def run_full_feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    df = create_time_features(df, dt_col="datetime")
    df = create_lag_features(df)
    df = create_rolling_features(df)
    df = create_ewm_features(df)
    df = create_history_group_features(df)
    df = add_safe_business_features(df)
    return df


def build_same_hour_proxy(
    history_df: pd.DataFrame,
    target_index: pd.DatetimeIndex,
    value_col: str,
    fallback_window_hours: int = 168,
) -> pd.Series:
    history = history_df[["datetime", value_col]].dropna().copy()
    if history.empty:
        return pd.Series(np.zeros(len(target_index), dtype=float), index=target_index)

    history = history.sort_values("datetime").reset_index(drop=True)
    history[value_col] = pd.to_numeric(history[value_col], errors="coerce")
    history["hour"] = history["datetime"].dt.hour

    by_dt = history.set_index("datetime")[value_col]
    by_hour_mean = history.groupby("hour")[value_col].mean().to_dict()
    recent_mean = float(history[value_col].tail(min(fallback_window_hours, len(history))).mean())
    if not np.isfinite(recent_mean):
        recent_mean = float(history[value_col].mean())
    if not np.isfinite(recent_mean):
        recent_mean = 0.0

    values = []
    for dt in target_index:
        candidate = by_dt.get(dt - pd.Timedelta(hours=24))
        if pd.isna(candidate):
            candidate = by_dt.get(dt - pd.Timedelta(hours=168))
        if pd.isna(candidate):
            candidate = by_hour_mean.get(int(dt.hour), recent_mean)
        if pd.isna(candidate):
            candidate = recent_mean
        values.append(float(candidate))
    return pd.Series(values, index=target_index, dtype=float)


def fetch_forward_weather_forecast(target_index: pd.DatetimeIndex) -> pd.DataFrame:
    if len(target_index) == 0:
        return pd.DataFrame(columns=["datetime", "temperature", "wind_speed", "precipitation", "future_weather_source"])

    target_max_date = pd.Timestamp(target_index.max()).normalize()
    current_eastern_date = pd.Timestamp.now(tz=WEATHER_TIMEZONE_NAME).tz_localize(None).normalize()
    if target_max_date < current_eastern_date:
        return pd.DataFrame(columns=["datetime", "temperature", "wind_speed", "precipitation", "future_weather_source"])

    params = {
        "latitude": WEATHER_FORECAST_LAT,
        "longitude": WEATHER_FORECAST_LON,
        "hourly": "temperature_2m,wind_speed_10m,precipitation",
        "timezone": WEATHER_TIMEZONE_NAME,
        "start_date": target_index.min().date().isoformat(),
        "end_date": target_index.max().date().isoformat(),
        "forecast_days": max(1, (target_index.max().date() - target_index.min().date()).days + 1),
    }
    response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    hourly = payload.get("hourly", {})
    time_values = hourly.get("time", [])
    if not time_values:
        return pd.DataFrame(columns=["datetime", "temperature", "wind_speed", "precipitation", "future_weather_source"])

    forecast_df = pd.DataFrame({
        "datetime": pd.to_datetime(time_values),
        "temperature": hourly.get("temperature_2m", []),
        "wind_speed": hourly.get("wind_speed_10m", []),
        "precipitation": hourly.get("precipitation", []),
    })
    forecast_df["future_weather_source"] = "Open-Meteo Forecast API"
    forecast_df = forecast_df[forecast_df["datetime"].isin(target_index)].copy()
    return forecast_df.sort_values("datetime").reset_index(drop=True)


def build_forward_weather_features(history_df: pd.DataFrame, target_index: pd.DatetimeIndex) -> pd.DataFrame:
    proxy_df = pd.DataFrame({"datetime": target_index})
    proxy_df["temperature_proxy"] = build_same_hour_proxy(history_df, target_index, "temperature").values
    proxy_df["wind_speed_proxy"] = build_same_hour_proxy(history_df, target_index, "wind_speed").values
    proxy_df["precipitation_proxy"] = build_same_hour_proxy(history_df, target_index, "precipitation").values

    try:
        forecast_df = fetch_forward_weather_forecast(target_index)
    except Exception as exc:
        log_print(f"未来天气预报获取失败，改用历史滞后天气代理：{exc}")
        forecast_df = pd.DataFrame(columns=["datetime", "temperature", "wind_speed", "precipitation", "future_weather_source"])

    merged = proxy_df.merge(forecast_df, on="datetime", how="left")
    for weather_col in ["temperature", "wind_speed", "precipitation"]:
        merged[weather_col] = merged[weather_col].fillna(merged[f"{weather_col}_proxy"])

    merged["future_weather_source"] = np.where(
        merged["future_weather_source"].notna(),
        merged["future_weather_source"],
        "历史滞后天气代理",
    )
    return merged[["datetime", "temperature", "wind_speed", "precipitation", "future_weather_source"]]


def load_forward_forecast_loads(history_df: pd.DataFrame, anchor_dt: pd.Timestamp, horizon_hours: int = FORMAL_FORECAST_HOURS) -> pd.DataFrame:
    target_index = pd.date_range(anchor_dt + pd.Timedelta(hours=1), periods=horizon_hours, freq="H")
    selected_df = pd.DataFrame(columns=["datetime", "forecast_load", "forecast_evaluated_at", "forecast_evaluated_at_utc"])
    if os.path.exists(FORECAST_LOAD_SELECTED_FILE):
        selected_df = pd.read_excel(FORECAST_LOAD_SELECTED_FILE)
        selected_df["datetime"] = pd.to_datetime(selected_df["datetime"])
        if "forecast_evaluated_at" in selected_df.columns:
            selected_df["forecast_evaluated_at"] = pd.to_datetime(selected_df["forecast_evaluated_at"])
        if "forecast_evaluated_at_utc" in selected_df.columns:
            selected_df["forecast_evaluated_at_utc"] = pd.to_datetime(selected_df["forecast_evaluated_at_utc"])
        selected_df = selected_df[
            (selected_df["datetime"] > anchor_dt)
            & (selected_df["datetime"] <= anchor_dt + pd.Timedelta(hours=horizon_hours))
        ].copy()

    future_load = pd.DataFrame({"datetime": target_index}).merge(selected_df, on="datetime", how="left")
    forecast_proxy = build_same_hour_proxy(history_df, target_index, "forecast_load")
    future_load["forecast_load_source"] = np.where(future_load["forecast_load"].notna(), "PJM固定日前版本预测", "历史同小时代理")
    future_load["forecast_load"] = pd.to_numeric(future_load["forecast_load"], errors="coerce")
    future_load["forecast_load"] = future_load["forecast_load"].fillna(pd.Series(forecast_proxy.values, index=future_load.index))

    default_issue_time = anchor_dt + pd.Timedelta(minutes=45)
    future_load["forecast_evaluated_at"] = pd.to_datetime(future_load["forecast_evaluated_at"], errors="coerce").fillna(default_issue_time)
    if "forecast_evaluated_at_utc" not in future_load.columns:
        future_load["forecast_evaluated_at_utc"] = pd.NaT
    future_load["forecast_evaluated_at_utc"] = pd.to_datetime(future_load["forecast_evaluated_at_utc"], errors="coerce")
    return future_load.sort_values("datetime").reset_index(drop=True)


def build_formal_forward_base_frame(history_df: pd.DataFrame, anchor_dt: pd.Timestamp, horizon_hours: int = FORMAL_FORECAST_HOURS) -> pd.DataFrame:
    target_index = pd.date_range(anchor_dt + pd.Timedelta(hours=1), periods=horizon_hours, freq="H")
    future_df = load_forward_forecast_loads(history_df, anchor_dt, horizon_hours)
    future_df = future_df.merge(build_forward_weather_features(history_df, target_index), on="datetime", how="left")

    ratio_window = history_df[["actual_load", "forecast_load"]].dropna().tail(24).copy()
    if ratio_window.empty:
        actual_ratio = 1.0
    else:
        safe_ratio = ratio_window["actual_load"] / np.where(np.abs(ratio_window["forecast_load"]) < 1e-6, 1e-6, np.abs(ratio_window["forecast_load"]))
        actual_ratio = float(np.clip(np.nanmedian(safe_ratio), 0.85, 1.15))
        if not np.isfinite(actual_ratio):
            actual_ratio = 1.0

    future_df["actual_load"] = future_df["forecast_load"] * actual_ratio
    future_df["actual_load_proxy_source"] = f"forecast_load_bias_adjusted({actual_ratio:.4f})"
    future_df["price_spread_rt_minus_da"] = build_same_hour_proxy(history_df, target_index, "price_spread_rt_minus_da").values
    future_df["rt_spread_proxy_source"] = "历史同小时价差代理"

    for col in ["load_area", "forecast_area", "mkt_region", "nerc_region", "region_id", "node_id", "node_name"]:
        if col in history_df.columns and not history_df[col].dropna().empty:
            future_df[col] = history_df[col].dropna().iloc[-1]
        else:
            future_df[col] = ""
    if "is_holiday" in history_df.columns:
        future_df["is_holiday"] = 0
    future_df["forecast_anchor_time"] = anchor_dt
    future_df["forecast_mode"] = "正式前瞻版"
    return future_df


def generate_formal_forward_forecast(
    history_df: pd.DataFrame,
    feature_cols: List[str],
    artifacts: Dict,
    model_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    anchor_dt = history_df["datetime"].max()
    future_base_df = build_formal_forward_base_frame(history_df, anchor_dt, FORMAL_FORECAST_HOURS)
    running_df = history_df.copy()
    result_rows = []
    feature_rows = []

    for _, base_row in future_base_df.iterrows():
        candidate_df = pd.concat([running_df, pd.DataFrame([base_row])], ignore_index=True)
        candidate_df = candidate_df.sort_values("datetime").reset_index(drop=True)
        candidate_features_df = run_full_feature_engineering(candidate_df)
        current_feature_row = candidate_features_df.iloc[-1].copy()
        missing_columns = [name for name in feature_cols if name not in current_feature_row.index]
        if missing_columns:
            raise ValueError(f"MISSING_FEATURE: 未来特征缺失，禁止补 0：{missing_columns[:20]}")
        raw_feature_input = current_feature_row.loc[feature_cols]
        feature_input = pd.to_numeric(raw_feature_input, errors="coerce")
        illegal_values = raw_feature_input[raw_feature_input.notna() & feature_input.isna()].index.tolist()
        if illegal_values:
            raise ValueError(f"ILLEGAL_STRING: 未来特征包含非法值：{illegal_values[:20]}")
        null_features = feature_input[feature_input.isna()].index.tolist()
        if null_features:
            raise ValueError(f"NAN_FORBIDDEN: 未来特征包含空值，禁止默认填充：{null_features[:20]}")
        if not np.isfinite(feature_input.to_numpy(dtype=float)).all():
            raise ValueError("INF_FORBIDDEN: 未来特征包含 Inf 或 -Inf")

        future_X = pd.DataFrame([feature_input.to_numpy(dtype="float64")], columns=feature_cols, dtype="float64")
        base_pred = float(artifacts["final_base_model"].predict(future_X)[0])
        peak_pred = float(artifacts["final_peak_model"].predict(future_X)[0])
        risk_prob = float(get_classifier_proba(artifacts["final_classifier"], future_X)[0])
        p90_pred = np.nan
        if artifacts.get("final_p90_model") is not None:
            try:
                p90_pred = float(artifacts["final_p90_model"].predict(future_X)[0])
            except Exception:
                p90_pred = np.nan
        load_high_flag = 0
        if "forecast_load_roll_mean_168" in feature_input.index and pd.notna(feature_input.get("forecast_load_roll_mean_168")):
            load_high_flag = int(float(base_row["forecast_load"]) >= float(feature_input.get("forecast_load_roll_mean_168")))
        error_high_flag = int(float(feature_input.get("scenario_mae", 0.0) or 0.0) > 0.0)
        enhanced_pred, blend_weight = blend_predictions(
            np.array([base_pred]),
            np.array([peak_pred]),
            np.array([risk_prob]),
            np.array([int(current_feature_row["hour"] in PEAK_HOURS)]),
            artifacts["best_alpha"],
            artifacts["best_floor"],
            load_high_flag=np.array([load_high_flag]),
            error_high_flag=np.array([error_high_flag]),
            spike_threshold=float(artifacts.get("best_spike_threshold", 0.5)),
        )
        final_pred = float(enhanced_pred[0])
        final_blend_weight = float(blend_weight[0])

        result_rows.append({
            "datetime": base_row["datetime"],
            "forecast_anchor_time": anchor_dt,
            "forecast_evaluated_at": base_row.get("forecast_evaluated_at", pd.NaT),
            "forecast_mode": "正式前瞻版",
            "forecast_load": float(base_row["forecast_load"]),
            "forecast_load_source": base_row.get("forecast_load_source", ""),
            "future_weather_source": base_row.get("future_weather_source", ""),
            "actual_load_proxy": float(base_row["actual_load"]),
            "actual_load_proxy_source": base_row.get("actual_load_proxy_source", ""),
            "rt_spread_proxy": float(base_row["price_spread_rt_minus_da"]),
            "rt_spread_proxy_source": base_row.get("rt_spread_proxy_source", ""),
            "基础模型预测值": base_pred,
            "高峰专项模型预测值": peak_pred,
            "尖峰风险概率": risk_prob,
            "融合权重": final_blend_weight,
            "预测的未来24小时日前电价": final_pred,
            "raw_base_pred": base_pred,
            "peak_pred": peak_pred,
            "spike_prob": risk_prob,
            "dynamic_alpha": final_blend_weight,
            "blended_pred": final_pred,
            "p90_pred": p90_pred,
            "缺失特征填补数量": len(missing_features),
            "剩余缺失特征数量": len(remaining_missing),
        })

        feature_record = {"datetime": base_row["datetime"]}
        for feature_name in feature_cols:
            feature_record[feature_name] = float(feature_input[feature_name]) if pd.notna(feature_input[feature_name]) else np.nan
        feature_rows.append(feature_record)

        next_row = base_row.copy()
        next_row["da_price"] = final_pred
        running_df = pd.concat([running_df, pd.DataFrame([next_row])], ignore_index=True)

    result_df = pd.DataFrame(result_rows)
    feature_df = pd.DataFrame(feature_rows)
    return result_df, feature_df


# =========================
# 模型与高峰增强
# =========================
def get_model_candidates() -> List[Dict]:
    candidates = []

    XGBRegressor = try_import_xgboost()
    if XGBRegressor is not None:
        candidates.append({
            "name": "XGBoost_raw",
            "builder": lambda: XGBRegressor(
                n_estimators=160,
                max_depth=5,
                learning_rate=0.045,
                subsample=0.85,
                colsample_bytree=0.85,
                objective="reg:squarederror",
                tree_method="hist",
                random_state=RANDOM_STATE,
                n_jobs=4,
            )
        })
        candidates.append({
            "name": "XGBoost_Tuned",
            "builder": lambda: XGBRegressor(
                n_estimators=220,
                max_depth=4,
                learning_rate=0.025,
                subsample=0.82,
                colsample_bytree=0.82,
                min_child_weight=6,
                reg_alpha=0.15,
                reg_lambda=2.0,
                objective="reg:squarederror",
                tree_method="hist",
                random_state=RANDOM_STATE,
                n_jobs=4,
            )
        })
    else:
        log_print("WARNING: 未安装 xgboost，跳过 XGBoost_raw / XGBoost_Tuned。")

    LGBMRegressor = try_import_lightgbm()
    if LGBMRegressor is not None:
        candidates.append({
            "name": "LightGBM_raw",
            "builder": lambda: LGBMRegressor(
                n_estimators=180,
                learning_rate=0.045,
                num_leaves=31,
                subsample=0.85,
                colsample_bytree=0.85,
                random_state=RANDOM_STATE,
                verbose=-1,
            )
        })
        candidates.append({
            "name": "LightGBM_Tuned",
            "builder": lambda: LGBMRegressor(
                n_estimators=240,
                learning_rate=0.025,
                num_leaves=24,
                max_depth=7,
                min_child_samples=35,
                subsample=0.82,
                colsample_bytree=0.82,
                reg_alpha=0.15,
                reg_lambda=2.0,
                random_state=RANDOM_STATE,
                verbose=-1,
            )
        })
    else:
        log_print("WARNING: 未安装 lightgbm，跳过 LightGBM_raw / LightGBM_Tuned。")

    CatBoostRegressor = try_import_catboost_regressor()
    if CatBoostRegressor is not None:
        candidates.append({
            "name": "CatBoost_Tuned",
            "builder": lambda: CatBoostRegressor(
                    iterations=220,
                depth=6,
                learning_rate=0.035,
                loss_function="RMSE",
                l2_leaf_reg=5.0,
                random_seed=RANDOM_STATE,
                verbose=False,
                allow_writing_files=False,
            )
        })
    else:
        log_print("WARNING: 未安装 catboost，跳过 CatBoost_Tuned。")

    candidates.extend([
        {
            "name": "HistGB_raw",
            "builder": lambda: HistGradientBoostingRegressor(
                learning_rate=0.05,
                max_depth=6,
                max_iter=180,
                random_state=RANDOM_STATE,
            )
        },
        {
            "name": "ExtraTrees",
            "builder": lambda: ExtraTreesRegressor(
                n_estimators=180,
                max_depth=24,
                min_samples_split=3,
                min_samples_leaf=2,
                random_state=RANDOM_STATE,
                n_jobs=4,
            )
        },
        {
            "name": "HuberRegressor",
            "builder": lambda: make_pipeline(
                StandardScaler(),
                HuberRegressor(epsilon=1.45, alpha=0.0005, max_iter=220),
            )
        },
        {
            "name": "Ridge",
            "builder": lambda: make_pipeline(
                StandardScaler(),
                Ridge(alpha=10.0, random_state=RANDOM_STATE),
            )
        },
        {
            "name": "ElasticNet",
            "builder": lambda: make_pipeline(
                StandardScaler(),
                ElasticNet(alpha=0.002, l1_ratio=0.20, max_iter=800, random_state=RANDOM_STATE),
            )
        },
        {
            "name": "RandomForest_raw",
            "builder": lambda: RandomForestRegressor(
                n_estimators=160,
                max_depth=18,
                min_samples_split=4,
                min_samples_leaf=2,
                random_state=RANDOM_STATE,
                n_jobs=4,
            )
        },
        {
            "name": "线性回归",
            "builder": lambda: LinearRegression()
        },
    ])
    return candidates


def get_peak_specialist_candidates() -> List[Dict]:
    candidates = []
    XGBRegressor = try_import_xgboost()
    if XGBRegressor is not None:
        candidates.append({
            "name": "Peak_XGBoost",
            "builder": lambda: XGBRegressor(
                n_estimators=180,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.9,
                colsample_bytree=0.9,
                objective="reg:squarederror",
                tree_method="hist",
                random_state=RANDOM_STATE,
                n_jobs=4,
            )
        })
        candidates.append({
            "name": "Peak_XGBoost_Weighted",
            "builder": lambda: XGBRegressor(
                n_estimators=220,
                max_depth=5,
                learning_rate=0.03,
                subsample=0.88,
                colsample_bytree=0.88,
                min_child_weight=4,
                reg_alpha=0.1,
                reg_lambda=1.8,
                objective="reg:squarederror",
                tree_method="hist",
                random_state=RANDOM_STATE,
                n_jobs=4,
            )
        })
    else:
        log_print("WARNING: 未安装 xgboost，跳过 Peak_XGBoost / Peak_XGBoost_Weighted。")
    LGBMRegressor = try_import_lightgbm()
    if LGBMRegressor is not None:
        candidates.append({
            "name": "Peak_LightGBM_Weighted",
            "builder": lambda: LGBMRegressor(
                n_estimators=240,
                learning_rate=0.03,
                num_leaves=31,
                max_depth=8,
                min_child_samples=25,
                subsample=0.88,
                colsample_bytree=0.88,
                reg_alpha=0.1,
                reg_lambda=1.8,
                random_state=RANDOM_STATE,
                verbose=-1,
            )
        })
        candidates.append({
            "name": "Peak_Quantile_P90",
            "builder": lambda: LGBMRegressor(
                objective="quantile",
                alpha=0.90,
                n_estimators=200,
                learning_rate=0.035,
                num_leaves=24,
                min_child_samples=25,
                subsample=0.88,
                colsample_bytree=0.88,
                random_state=RANDOM_STATE,
                verbose=-1,
            )
        })
    else:
        log_print("WARNING: 未安装 lightgbm，跳过 Peak_LightGBM_Weighted 和 LightGBM 分位数模型。")
    CatBoostRegressor = try_import_catboost_regressor()
    if CatBoostRegressor is not None:
        candidates.append({
            "name": "Peak_CatBoost_Weighted",
            "builder": lambda: CatBoostRegressor(
                    iterations=240,
                depth=6,
                learning_rate=0.035,
                loss_function="RMSE",
                l2_leaf_reg=5.0,
                random_seed=RANDOM_STATE,
                verbose=False,
                allow_writing_files=False,
            )
        })
    else:
        log_print("WARNING: 未安装 catboost，跳过 Peak_CatBoost_Weighted。")
    candidates.extend([
        {
            "name": "Peak_HistGB",
            "builder": lambda: HistGradientBoostingRegressor(
                learning_rate=0.05,
                max_depth=7,
                max_iter=200,
                random_state=RANDOM_STATE,
            )
        },
        {
            "name": "Peak_ExtraTrees",
            "builder": lambda: ExtraTreesRegressor(
                n_estimators=200,
                max_depth=28,
                min_samples_split=3,
                min_samples_leaf=1,
                random_state=RANDOM_STATE,
                n_jobs=4,
            )
        },
        {
            "name": "Peak_Quantile_P90_HistGB",
            "builder": lambda: HistGradientBoostingRegressor(
                loss="quantile",
                quantile=0.90,
                learning_rate=0.04,
                max_depth=7,
                max_iter=200,
                random_state=RANDOM_STATE,
            )
        },
        {
            "name": "Peak_RandomForest",
            "builder": lambda: RandomForestRegressor(
                n_estimators=180,
                max_depth=22,
                min_samples_split=3,
                min_samples_leaf=1,
                random_state=RANDOM_STATE,
                n_jobs=4,
            )
        },
    ])
    return candidates


def get_peak_classifier_candidates() -> List[Dict]:
    XGBClassifier = None
    try:
        from xgboost import XGBClassifier
        XGBClassifier = XGBClassifier
    except Exception:
        log_print("WARNING: 未安装 xgboost，跳过 Spike_XGBoost_Classifier。")
    LGBMClassifier = try_import_lightgbm_classifier()
    if LGBMClassifier is None:
        log_print("WARNING: 未安装 lightgbm，跳过 Spike_LightGBM_Classifier。")
    CatBoostClassifier = try_import_catboost_classifier()
    if CatBoostClassifier is None:
        log_print("WARNING: 未安装 catboost，跳过 Spike_CatBoost_Classifier。")
    candidates = [
        *([
            {
                "name": "Spike_LightGBM_Classifier",
                "builder": lambda: LGBMClassifier(
                    n_estimators=220,
                    learning_rate=0.03,
                    num_leaves=31,
                    max_depth=7,
                    min_child_samples=20,
                    subsample=0.88,
                    colsample_bytree=0.88,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                    verbose=-1,
                )
            }
        ] if LGBMClassifier is not None else []),
        *([
            {
                "name": "Spike_XGBoost_Classifier",
                "builder": lambda: XGBClassifier(
                    n_estimators=220,
                    max_depth=5,
                    learning_rate=0.035,
                    subsample=0.88,
                    colsample_bytree=0.88,
                    min_child_weight=3,
                    reg_lambda=2.0,
                    objective="binary:logistic",
                    eval_metric="logloss",
                    tree_method="hist",
                    random_state=RANDOM_STATE,
                    n_jobs=4,
                )
            }
        ] if XGBClassifier is not None else []),
        *([
            {
                "name": "Spike_CatBoost_Classifier",
                "builder": lambda: CatBoostClassifier(
                    iterations=220,
                    depth=5,
                    learning_rate=0.035,
                    loss_function="Logloss",
                    auto_class_weights="Balanced",
                    random_seed=RANDOM_STATE,
                    verbose=False,
                    allow_writing_files=False,
                )
            }
        ] if CatBoostClassifier is not None else []),
        {
            "name": "Spike_RF_Classifier",
            "builder": lambda: RandomForestClassifier(
                n_estimators=180,
                max_depth=12,
                min_samples_leaf=2,
                random_state=RANDOM_STATE,
                n_jobs=4,
                class_weight="balanced",
            )
        },
        {
            "name": "Spike_HGB_Classifier",
            "builder": lambda: HistGradientBoostingClassifier(
                learning_rate=0.05,
                max_depth=6,
                max_iter=180,
                random_state=RANDOM_STATE,
            )
        },
        {
            "name": "Calibrated_Logistic",
            "builder": lambda: CalibratedClassifierCV(
                LogisticRegression(
                    max_iter=600,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
                method="sigmoid",
                cv=3,
            )
        },
        {
            "name": "Spike_Logistic",
            "builder": lambda: LogisticRegression(
                max_iter=600,
                class_weight="balanced",
                random_state=RANDOM_STATE,
            )
        },
    ]
    return candidates


def fit_and_predict_reg(model_info: Dict, X_train, y_train, X_valid, sample_weight=None):
    model = model_info["builder"]()
    fit_model_with_optional_weight(model, X_train, y_train, sample_weight=sample_weight)
    pred = model.predict(X_valid)
    return model, pred


def fit_classifier_and_predict_proba(model_info: Dict, X_train, y_train_cls, X_valid, sample_weight=None):
    model = model_info["builder"]()
    fit_model_with_optional_weight(model, X_train, y_train_cls, sample_weight=sample_weight)
    proba = safe_predict_proba(model, X_valid)
    return model, proba


def safe_predict_proba(model, X):
    if model is None:
        return np.zeros(len(X), dtype=float)
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        if getattr(proba, "ndim", 1) == 2 and proba.shape[1] > 1:
            return np.asarray(proba[:, 1], dtype=float)
        return np.asarray(proba, dtype=float).ravel()
    if hasattr(model, "decision_function"):
        score = np.asarray(model.decision_function(X), dtype=float)
        return 1.0 / (1.0 + np.exp(-np.clip(score, -50, 50)))
    return np.asarray(model.predict(X), dtype=float)


def evaluate_classifier_thresholds(y_true, proba, model_name: str) -> Tuple[Dict, pd.DataFrame]:
    y_arr = np.asarray(y_true, dtype=int)
    p_arr = np.asarray(proba, dtype=float)
    records = []
    for threshold in SPIKE_THRESHOLD_GRID:
        pred_label = (p_arr >= float(threshold)).astype(int)
        precision, recall, f1, _ = precision_recall_fscore_support(y_arr, pred_label, average="binary", zero_division=0)
        tn, fp, fn, tp = confusion_matrix(y_arr, pred_label, labels=[0, 1]).ravel()
        records.append({
            "模型": model_name,
            "threshold": float(threshold),
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        })
    threshold_df = pd.DataFrame(records)
    preferred = threshold_df[threshold_df["recall"] >= 0.70]
    best = (preferred if not preferred.empty else threshold_df).sort_values(["f1", "recall", "precision"], ascending=False).iloc[0].to_dict()
    try:
        roc_auc = float(roc_auc_score(y_arr, p_arr)) if len(np.unique(y_arr)) > 1 else np.nan
    except Exception:
        roc_auc = np.nan
    try:
        pr_auc = float(average_precision_score(y_arr, p_arr)) if len(np.unique(y_arr)) > 1 else np.nan
    except Exception:
        pr_auc = np.nan
    best["roc_auc"] = roc_auc
    best["pr_auc"] = pr_auc
    best["best_spike_threshold"] = best["threshold"]
    return best, threshold_df


def build_peak_spike_label(df_part: pd.DataFrame, y_series: pd.Series) -> Tuple[pd.Series, Dict]:
    hour_series = df_part["hour"]
    peak_mask = hour_series.isin(PEAK_HOURS)
    y_numeric = pd.to_numeric(y_series, errors="coerce")
    global_q90 = float(y_series.quantile(0.90))
    global_q95 = float(y_series.quantile(0.95))
    if peak_mask.sum() >= 50:
        peak_q80 = float(y_series[peak_mask].quantile(0.80))
        morning_q80 = float(y_series[df_part["hour"].isin(MORNING_PEAK_HOURS)].quantile(0.80)) if df_part["hour"].isin(MORNING_PEAK_HOURS).sum() >= 20 else peak_q80
    else:
        peak_q80 = global_q90
        morning_q80 = global_q90

    rolling_90 = y_numeric.shift(1).rolling(window=24 * 30, min_periods=24 * 7).quantile(0.90).fillna(global_q90)
    price_change_1h = y_numeric.diff().abs()
    change_q90 = float(price_change_1h.shift(1).quantile(0.90)) if price_change_1h.notna().sum() >= 20 else 0.0
    peak_hour_p80 = float(y_numeric[peak_mask].quantile(0.80)) if peak_mask.sum() >= 20 else peak_q80

    label = (
        (y_numeric >= rolling_90)
        | (y_numeric >= global_q90)
        | (price_change_1h >= change_q90)
        | ((df_part["hour"].isin(PEAK_HOURS)) & (y_numeric >= peak_hour_p80))
    ).fillna(False).astype(int)

    thresholds = {
        "global_q90": global_q90,
        "global_q95": global_q95,
        "peak_q80": peak_q80,
        "morning_q80": morning_q80,
        "rolling_90_window_hours": 24 * 30,
        "change_q90": change_q90,
        "peak_hour_p80": peak_hour_p80,
    }
    return label, thresholds


def build_peak_sample_weight(df_part: pd.DataFrame, y_series: pd.Series, peak_label: pd.Series, thresholds: Dict) -> np.ndarray:
    weights = np.ones(len(df_part), dtype=float)
    hour = df_part["hour"]
    y_numeric = pd.to_numeric(y_series, errors="coerce")
    p75 = float(y_numeric.quantile(0.75))
    p90 = float(y_numeric.quantile(0.90))
    weights += 1.5 * hour.isin(MORNING_PEAK_HOURS + EVENING_PEAK_HOURS).astype(float).values
    weights += 1.5 * ((y_numeric >= p75) & (y_numeric < p90)).astype(float).values
    weights += 3.0 * (y_numeric >= p90).astype(float).values
    weights += 4.0 * peak_label.values.astype(float)
    if "scenario_mae" in df_part.columns:
        scenario_mae = pd.to_numeric(df_part["scenario_mae"], errors="coerce")
        if scenario_mae.notna().sum() >= 20:
            high_error_threshold = scenario_mae.quantile(0.80)
            weights += 2.0 * (scenario_mae >= high_error_threshold).fillna(False).astype(float).values
    weights = np.clip(weights, 1.0, 8.0)
    return weights


def safe_rmse(y_true, pred) -> float:
    y_arr = np.array(y_true, dtype=float)
    p_arr = np.array(pred, dtype=float)
    mask = np.isfinite(y_arr) & np.isfinite(p_arr)
    if mask.sum() == 0:
        return float("nan")
    return float(np.sqrt(mean_squared_error(y_arr[mask], p_arr[mask])))


def safe_mae(y_true, pred) -> float:
    y_arr = np.array(y_true, dtype=float)
    p_arr = np.array(pred, dtype=float)
    mask = np.isfinite(y_arr) & np.isfinite(p_arr)
    if mask.sum() == 0:
        return float("nan")
    return float(mean_absolute_error(y_arr[mask], p_arr[mask]))


def calc_custom_score(y_true, pred, hours, spike_label_eval):
    overall = evaluate_regression(y_true, pred, "tmp")
    peak_mask = pd.Series(hours).isin(PEAK_HOURS).values
    spike_mask = np.array(spike_label_eval).astype(bool)

    rmse_peak = safe_rmse(np.array(y_true)[peak_mask], np.array(pred)[peak_mask]) if peak_mask.sum() > 0 else overall["RMSE"]
    rmse_spike = safe_rmse(np.array(y_true)[spike_mask], np.array(pred)[spike_mask]) if spike_mask.sum() > 0 else overall["RMSE"]

    # 兼顾整体与高峰尖刺：值越小越好
    score = 0.45 * overall["RMSE"] + 0.25 * rmse_peak + 0.20 * rmse_spike + 0.10 * overall["MAE"]
    return score, overall, rmse_peak, rmse_spike


def _is_complex_model(model_name: str) -> bool:
    simple_names = ["线性回归", "Ridge", "ElasticNet", "HuberRegressor"]
    return not any(name in str(model_name) for name in simple_names)


def _overfit_status(model_name: str, train_rmse: float, val_rmse: float) -> tuple[float, int, str]:
    if not np.isfinite(train_rmse) or not np.isfinite(val_rmse):
        return float("nan"), 0, "指标不足"
    gap = float(val_rmse - train_rmse)
    ratio = float(val_rmse / max(train_rmse, 1e-6))
    overfit = int(_is_complex_model(model_name) and train_rmse > 0 and (ratio >= 1.50 or gap >= max(8.0, train_rmse * 0.45)))
    return gap, overfit, "明显过拟合，禁止入选最佳" if overfit else "正常"


def _regression_diagnostic_row(
    model_name: str,
    y_train,
    pred_train,
    y_val,
    pred_val,
    val_df: pd.DataFrame,
    val_spike_label: pd.Series,
    y_test=None,
    pred_test=None,
    test_df: pd.DataFrame | None = None,
    test_spike_label: pd.Series | None = None,
    score_mode: str = "base",
) -> Dict:
    train_mae = safe_mae(y_train, pred_train)
    train_rmse = safe_rmse(y_train, pred_train)
    val_mae = safe_mae(y_val, pred_val)
    val_rmse = safe_rmse(y_val, pred_val)
    val_peak_mask = val_df["hour"].isin(PEAK_HOURS).values
    val_spike_mask = np.array(val_spike_label).astype(bool)
    peak_rmse = safe_rmse(np.array(y_val)[val_peak_mask], np.array(pred_val)[val_peak_mask]) if val_peak_mask.sum() > 0 else val_rmse
    spike_rmse = safe_rmse(np.array(y_val)[val_spike_mask], np.array(pred_val)[val_spike_mask]) if val_spike_mask.sum() > 0 else val_rmse
    peak_bias = float(np.nanmean(np.array(pred_val)[val_peak_mask] - np.array(y_val)[val_peak_mask])) if val_peak_mask.sum() > 0 else 0.0
    bias_mean = float(np.nanmean(np.array(pred_val) - np.array(y_val)))
    overfit_gap, overfit_flag, overfit_reason = _overfit_status(model_name, train_rmse, val_rmse)
    if score_mode == "peak":
        score = 0.45 * peak_rmse + 0.25 * spike_rmse + 0.20 * val_rmse + 0.10 * abs(peak_bias)
    else:
        score = 0.45 * val_rmse + 0.25 * peak_rmse + 0.20 * spike_rmse + 0.10 * val_mae
    if overfit_flag:
        score = float(score) + 1e6
    row = {
        "模型": model_name,
        "train_MAE": train_mae,
        "train_RMSE": train_rmse,
        "val_MAE": val_mae,
        "val_RMSE": val_rmse,
        "test_MAE": np.nan,
        "test_RMSE": np.nan,
        "MAE": val_mae,
        "RMSE": val_rmse,
        "峰时段RMSE": peak_rmse,
        "尖峰样本RMSE": spike_rmse,
        "peak_RMSE": peak_rmse,
        "spike_RMSE": spike_rmse,
        "bias_mean": bias_mean,
        "peak_bias_abs": abs(peak_bias),
        "overfit_gap": overfit_gap,
        "overfit_flag": overfit_flag,
        "overfit_reason": overfit_reason,
        "综合评分(越低越好)": score,
    }
    if y_test is not None and pred_test is not None:
        row["test_MAE"] = safe_mae(y_test, pred_test)
        row["test_RMSE"] = safe_rmse(y_test, pred_test)
        if test_df is not None:
            test_peak_mask = test_df["hour"].isin(PEAK_HOURS).values
            row["test_peak_RMSE"] = safe_rmse(np.array(y_test)[test_peak_mask], np.array(pred_test)[test_peak_mask]) if test_peak_mask.sum() > 0 else row["test_RMSE"]
        if test_spike_label is not None:
            test_spike_mask = np.array(test_spike_label).astype(bool)
            row["test_spike_RMSE"] = safe_rmse(np.array(y_test)[test_spike_mask], np.array(pred_test)[test_spike_mask]) if test_spike_mask.sum() > 0 else row["test_RMSE"]
    return row


def select_best_base_model(X_train, y_train, train_df, X_val, y_val, val_df, X_test=None, y_test=None, test_df=None):
    val_peak_label, val_thresholds = build_peak_spike_label(val_df, y_val)
    records = []
    fitted_models = {}

    train_peak_label, train_thresholds = build_peak_spike_label(train_df, y_train)
    train_weights = build_peak_sample_weight(train_df, y_train, train_peak_label, train_thresholds)
    test_peak_label = build_peak_spike_label(test_df, y_test)[0] if test_df is not None and y_test is not None else None

    for model_info in get_model_candidates():
        model_name = model_info["name"]
        try:
            # 基础模型用轻度峰值加权，帮助候选阶段更关注高峰表现
            model, pred = fit_and_predict_reg(model_info, X_train, y_train, X_val, sample_weight=train_weights)
            pred_train = model.predict(X_train)
            pred_test = model.predict(X_test) if X_test is not None else None
            row = _regression_diagnostic_row(
                model_name,
                y_train,
                pred_train,
                y_val,
                pred,
                val_df,
                val_peak_label,
                y_test=y_test,
                pred_test=pred_test,
                test_df=test_df,
                test_spike_label=test_peak_label,
                score_mode="base",
            )
            records.append(row)
            fitted_models[model_name] = model
            log_print(
                f"候选基础模型 {model_name}：综合评分={row['综合评分(越低越好)']:.6f}, "
                f"val_RMSE={row['val_RMSE']:.6f}, 峰RMSE={row['峰时段RMSE']:.6f}, "
                f"尖峰RMSE={row['尖峰样本RMSE']:.6f}, overfit={row['overfit_reason']}"
            )
        except Exception as e:
            log_print(f"候选基础模型 {model_name} 运行失败，原因：{e}")

    result_df = pd.DataFrame(records).sort_values(["综合评分(越低越好)", "RMSE", "MAE"]).reset_index(drop=True)
    if result_df.empty:
        raise RuntimeError("所有候选基础模型均失败，请检查环境或数据。")
    selectable = result_df[result_df["overfit_flag"].fillna(0).astype(int) == 0]
    if selectable.empty:
        log_print("WARNING: 所有基础候选模型均存在过拟合标记，退回选择评分最低模型。")
        selectable = result_df
    best_name = selectable.sort_values(["综合评分(越低越好)", "RMSE", "MAE"]).iloc[0]["模型"]
    return best_name, fitted_models[best_name], result_df, train_peak_label, train_thresholds, train_weights


def select_best_peak_specialist(X_train, y_train, train_df, X_val, y_val, val_df, train_peak_label, train_thresholds, X_test=None, y_test=None, test_df=None):
    records = []
    fitted_models = {}
    train_weights = build_peak_sample_weight(train_df, y_train, train_peak_label, train_thresholds)
    val_peak_label, _ = build_peak_spike_label(val_df, y_val)
    test_peak_label = build_peak_spike_label(test_df, y_test)[0] if test_df is not None and y_test is not None else None

    for model_info in get_peak_specialist_candidates():
        model_name = model_info["name"]
        try:
            model, pred = fit_and_predict_reg(model_info, X_train, y_train, X_val, sample_weight=train_weights)
            pred_train = model.predict(X_train)
            pred_test = model.predict(X_test) if X_test is not None else None
            row = _regression_diagnostic_row(
                model_name,
                y_train,
                pred_train,
                y_val,
                pred,
                val_df,
                val_peak_label,
                y_test=y_test,
                pred_test=pred_test,
                test_df=test_df,
                test_spike_label=test_peak_label,
                score_mode="peak",
            )
            records.append(row)
            fitted_models[model_name] = model
            log_print(
                f"候选高峰专项模型 {model_name}：综合评分={row['综合评分(越低越好)']:.6f}, "
                f"峰RMSE={row['峰时段RMSE']:.6f}, 尖峰RMSE={row['尖峰样本RMSE']:.6f}, "
                f"peak_bias_abs={row['peak_bias_abs']:.6f}, overfit={row['overfit_reason']}"
            )
        except Exception as e:
            log_print(f"候选高峰专项模型 {model_name} 运行失败，原因：{e}")

    result_df = pd.DataFrame(records).sort_values(["综合评分(越低越好)", "峰时段RMSE", "尖峰样本RMSE"]).reset_index(drop=True)
    if result_df.empty:
        raise RuntimeError("所有高峰专项模型均失败，请检查环境或数据。")
    selectable = result_df[result_df["overfit_flag"].fillna(0).astype(int) == 0]
    if selectable.empty:
        log_print("WARNING: 所有高峰候选模型均存在过拟合标记，退回选择评分最低模型。")
        selectable = result_df
    best_name = selectable.sort_values(["综合评分(越低越好)", "峰时段RMSE", "尖峰样本RMSE"]).iloc[0]["模型"]
    return best_name, fitted_models[best_name], result_df


def select_best_peak_classifier(X_train, train_df, train_peak_label, X_val, val_df, y_val):
    records = []
    fitted_models = {}
    positive_count = int((train_peak_label.values == 1).sum())
    negative_count = max(1, int((train_peak_label.values == 0).sum()))
    pos_weight = min(12.0, max(1.0, negative_count / max(1, positive_count)))
    cls_weight = np.where(train_peak_label.values == 1, pos_weight, 1.0)

    val_peak_label, _ = build_peak_spike_label(val_df, y_val)
    threshold_tables = []
    for model_info in get_peak_classifier_candidates():
        model_name = model_info["name"]
        try:
            model, proba = fit_classifier_and_predict_proba(model_info, X_train, train_peak_label, X_val, sample_weight=cls_weight)
            pos_mean = float(np.mean(proba[val_peak_label.values == 1])) if (val_peak_label.values == 1).sum() > 0 else 0.0
            neg_mean = float(np.mean(proba[val_peak_label.values == 0])) if (val_peak_label.values == 0).sum() > 0 else 0.0
            sep = pos_mean - neg_mean
            best_threshold, threshold_df = evaluate_classifier_thresholds(val_peak_label.values, proba, model_name)
            threshold_tables.append(threshold_df)
            records.append({
                "模型": model_name,
                "正例平均概率": pos_mean,
                "负例平均概率": neg_mean,
                "区分度": sep,
                "precision": best_threshold["precision"],
                "recall": best_threshold["recall"],
                "f1": best_threshold["f1"],
                "roc_auc": best_threshold["roc_auc"],
                "pr_auc": best_threshold["pr_auc"],
                "best_spike_threshold": best_threshold["best_spike_threshold"],
                "tn": best_threshold["tn"],
                "fp": best_threshold["fp"],
                "fn": best_threshold["fn"],
                "tp": best_threshold["tp"],
                "class_pos_weight": pos_weight,
            })
            fitted_models[model_name] = model
            log_print(
                f"候选尖峰分类器 {model_name}：F1={best_threshold['f1']:.6f}, "
                f"Recall={best_threshold['recall']:.6f}, Precision={best_threshold['precision']:.6f}, "
                f"PR_AUC={best_threshold['pr_auc']:.6f}, threshold={best_threshold['best_spike_threshold']:.2f}"
            )
        except Exception as e:
            log_print(f"候选尖峰分类器 {model_name} 运行失败，原因：{e}")

    result_df = pd.DataFrame(records).sort_values(["f1", "recall", "pr_auc", "区分度"], ascending=False).reset_index(drop=True)
    if result_df.empty:
        return None, None, pd.DataFrame(columns=["模型", "正例平均概率", "负例平均概率", "区分度"]), 0.5, pd.DataFrame()
    best_name = result_df.loc[0, "模型"]
    best_threshold = float(result_df.loc[0, "best_spike_threshold"])
    all_thresholds = pd.concat(threshold_tables, ignore_index=True) if threshold_tables else pd.DataFrame()
    return best_name, fitted_models[best_name], result_df, best_threshold, all_thresholds


def get_classifier_proba(model, X):
    return safe_predict_proba(model, X)


def blend_predictions(base_pred, peak_pred, risk_prob, peak_hour_flag, alpha: float, peak_floor: float, load_high_flag=None, error_high_flag=None, spike_threshold: float = 0.5):
    risk_prob = np.clip(np.array(risk_prob, dtype=float), 0.0, 1.0)
    peak_hour_flag = np.array(peak_hour_flag, dtype=float)
    load_high_flag = np.zeros_like(risk_prob) if load_high_flag is None else np.array(load_high_flag, dtype=float)
    error_high_flag = np.zeros_like(risk_prob) if error_high_flag is None else np.array(error_high_flag, dtype=float)
    dynamic_alpha = (
        float(alpha)
        + 0.12 * peak_hour_flag
        + 0.18 * (risk_prob >= float(spike_threshold)).astype(float)
        + 0.10 * load_high_flag
        + 0.08 * error_high_flag
    )
    dynamic_alpha = np.maximum(dynamic_alpha, float(peak_floor) * peak_hour_flag)
    dynamic_alpha = np.clip(dynamic_alpha, 0.0, 0.65)
    final_pred = np.array(base_pred, dtype=float) * (1.0 - dynamic_alpha) + np.array(peak_pred, dtype=float) * dynamic_alpha
    return final_pred, dynamic_alpha


def search_best_blend(base_pred_val, peak_pred_val, risk_prob_val, val_df, y_val, spike_threshold: float = 0.5) -> Tuple[float, float, pd.DataFrame]:
    val_peak_label, _ = build_peak_spike_label(val_df, y_val)
    records = []
    best_alpha, best_floor, best_score = 0.0, 0.0, np.inf
    load_high = np.zeros(len(val_df), dtype=float)
    if "forecast_load" in val_df.columns:
        load_q80 = pd.to_numeric(val_df["forecast_load"], errors="coerce").quantile(0.80)
        load_high = (pd.to_numeric(val_df["forecast_load"], errors="coerce") >= load_q80).fillna(False).astype(float).values
    error_high = np.zeros(len(val_df), dtype=float)
    if "scenario_mae" in val_df.columns:
        err_q80 = pd.to_numeric(val_df["scenario_mae"], errors="coerce").quantile(0.80)
        error_high = (pd.to_numeric(val_df["scenario_mae"], errors="coerce") >= err_q80).fillna(False).astype(float).values

    for alpha in BLEND_ALPHA_GRID:
        if alpha > 0.65:
            continue
        for floor in PEAK_FLOOR_GRID:
            final_pred, blend_weight = blend_predictions(
                base_pred_val,
                peak_pred_val,
                risk_prob_val,
                val_df["hour"].isin(PEAK_HOURS).astype(int).values,
                alpha,
                floor,
                load_high_flag=load_high,
                error_high_flag=error_high,
                spike_threshold=spike_threshold,
            )
            score, overall, rmse_peak, rmse_spike = calc_custom_score(y_val, final_pred, val_df["hour"], val_peak_label)
            records.append({
                "base_alpha": alpha,
                "peak_floor": floor,
                "RMSE": overall["RMSE"],
                "MAE": overall["MAE"],
                "MAPE(%)": overall["MAPE(%)"],
                "R2": overall["R2"],
                "峰时段RMSE": rmse_peak,
                "尖峰样本RMSE": rmse_spike,
                "平均dynamic_alpha": float(np.mean(blend_weight)),
                "最大dynamic_alpha": float(np.max(blend_weight)),
                "综合评分(越低越好)": score,
            })
            if score < best_score:
                best_score = score
                best_alpha = alpha
                best_floor = floor
    result_df = pd.DataFrame(records).sort_values(["综合评分(越低越好)", "RMSE"]).reset_index(drop=True)
    return best_alpha, best_floor, result_df


def get_feature_importance(model, feature_names: List[str]) -> pd.DataFrame:
    if hasattr(model, "feature_importances_"):
        return pd.DataFrame({"特征": feature_names, "重要性": model.feature_importances_}).sort_values("重要性", ascending=False)
    if hasattr(model, "coef_"):
        coef = np.ravel(np.array(model.coef_))
        return pd.DataFrame({"特征": feature_names, "重要性": np.abs(coef)}).sort_values("重要性", ascending=False)
    return pd.DataFrame(columns=["特征", "重要性"])


# =========================
# 异常识别与回测
# =========================
def identify_anomalies(pred_df: pd.DataFrame) -> pd.DataFrame:
    pred_df = pred_df.copy()
    pred_df["绝对误差"] = np.abs(pred_df["预测误差"])
    pred_df["相对误差(%)"] = np.abs(pred_df["预测误差"]) / np.where(np.abs(pred_df["真实值"]) < 1e-6, 1e-6, np.abs(pred_df["真实值"])) * 100

    q99 = pred_df["绝对误差"].quantile(0.99)
    threshold = max(ANOMALY_MIN_ABS_ERROR, q99)
    pred_df["是否异常"] = (pred_df["绝对误差"] >= threshold).astype(int)

    spike_threshold = pred_df["真实值"].quantile(0.95)
    pred_df["是否尖峰价"] = (pred_df["真实值"] >= spike_threshold).astype(int)

    pred_df["hour"] = pd.to_datetime(pred_df["datetime"]).dt.hour
    pred_df["是否高峰时段"] = pred_df["hour"].isin(PEAK_HOURS).astype(int)
    pred_df["是否晨峰"] = pred_df["hour"].isin(MORNING_PEAK_HOURS).astype(int)
    pred_df["是否晚峰"] = pred_df["hour"].isin(EVENING_PEAK_HOURS).astype(int)
    return pred_df.sort_values("绝对误差", ascending=False)


def run_peak_enhanced_pipeline(train_df, val_df, test_df, feature_cols, save_validation_artifacts=False):
    X_train = train_df[feature_cols]
    y_train = train_df[TARGET_COL]
    X_val = val_df[feature_cols]
    y_val = val_df[TARGET_COL]
    X_test = test_df[feature_cols]
    y_test = test_df[TARGET_COL]

    # 1）选择基础模型（兼顾整体与高峰）
    base_name, _, base_val_df, train_peak_label, train_thresholds, _ = select_best_base_model(X_train, y_train, train_df, X_val, y_val, val_df, X_test=X_test, y_test=y_test, test_df=test_df)

    # 2）在 train 上重训基础模型并得到验证预测
    base_info = [m for m in get_model_candidates() if m["name"] == base_name][0]
    peak_train_weights = build_peak_sample_weight(train_df, y_train, train_peak_label, train_thresholds)
    base_model, base_pred_val = fit_and_predict_reg(base_info, X_train, y_train, X_val, sample_weight=peak_train_weights)

    # 3）选择高峰专项模型（更偏重尖峰/峰时段）
    peak_name, _, peak_val_df = select_best_peak_specialist(X_train, y_train, train_df, X_val, y_val, val_df, train_peak_label, train_thresholds, X_test=X_test, y_test=y_test, test_df=test_df)
    peak_info = [m for m in get_peak_specialist_candidates() if m["name"] == peak_name][0]
    peak_model, peak_pred_val = fit_and_predict_reg(peak_info, X_train, y_train, X_val, sample_weight=peak_train_weights)

    # 4）训练尖峰风险分类器
    cls_name, cls_model, cls_val_df, best_spike_threshold, cls_threshold_df = select_best_peak_classifier(X_train, train_df, train_peak_label, X_val, val_df, y_val)
    risk_prob_val = get_classifier_proba(cls_model, X_val)

    # 5）验证集搜索融合强度 alpha / peak_floor
    best_alpha, best_floor, blend_search_df = search_best_blend(base_pred_val, peak_pred_val, risk_prob_val, val_df, y_val, spike_threshold=best_spike_threshold)
    enhanced_pred_val, blend_weight_val = blend_predictions(base_pred_val, peak_pred_val, risk_prob_val, val_df["hour"].isin(PEAK_HOURS).astype(int).values, best_alpha, best_floor, spike_threshold=best_spike_threshold)

    # 6）训练+验证重训最终模型
    train_val_df = pd.concat([train_df, val_df], axis=0).reset_index(drop=True)
    X_train_val = train_val_df[feature_cols]
    y_train_val = train_val_df[TARGET_COL]
    train_val_peak_label, train_val_thresholds = build_peak_spike_label(train_val_df, y_train_val)
    train_val_weights = build_peak_sample_weight(train_val_df, y_train_val, train_val_peak_label, train_val_thresholds)

    final_base_model = base_info["builder"]()
    fit_model_with_optional_weight(final_base_model, X_train_val, y_train_val, sample_weight=train_val_weights)
    base_pred_test = final_base_model.predict(X_test)

    final_peak_model = peak_info["builder"]()
    fit_model_with_optional_weight(final_peak_model, X_train_val, y_train_val, sample_weight=train_val_weights)
    peak_pred_test = final_peak_model.predict(X_test)

    final_p90_model = None
    p90_pred_test = np.repeat(np.nan, len(X_test))
    quantile_candidates = [m for m in get_peak_specialist_candidates() if "Quantile" in m["name"]]
    if quantile_candidates:
        try:
            q_info = quantile_candidates[0]
            final_p90_model = q_info["builder"]()
            fit_model_with_optional_weight(final_p90_model, X_train_val, y_train_val, sample_weight=train_val_weights)
            p90_pred_test = final_p90_model.predict(X_test)
        except Exception as exc:
            final_p90_model = None
            log_print(f"WARNING: P90 分位数模型训练失败，跳过 p90_pred 输出：{exc}")

    final_cls_model = None
    if cls_model is not None and cls_name is not None:
        cls_info = [m for m in get_peak_classifier_candidates() if m["name"] == cls_name][0]
        final_cls_model = cls_info["builder"]()
        pos = max(1, int((train_val_peak_label.values == 1).sum()))
        neg = max(1, int((train_val_peak_label.values == 0).sum()))
        cls_weight = np.where(train_val_peak_label.values == 1, min(12.0, max(1.0, neg / pos)), 1.0)
        fit_model_with_optional_weight(final_cls_model, X_train_val, train_val_peak_label, sample_weight=cls_weight)
    risk_prob_test = get_classifier_proba(final_cls_model, X_test)

    load_high_test = np.zeros(len(test_df), dtype=float)
    if "forecast_load" in test_df.columns:
        load_q80 = pd.to_numeric(train_val_df["forecast_load"], errors="coerce").quantile(0.80) if "forecast_load" in train_val_df.columns else pd.to_numeric(test_df["forecast_load"], errors="coerce").quantile(0.80)
        load_high_test = (pd.to_numeric(test_df["forecast_load"], errors="coerce") >= load_q80).fillna(False).astype(float).values
    enhanced_pred_test, blend_weight_test = blend_predictions(
        base_pred_test,
        peak_pred_test,
        risk_prob_test,
        test_df["hour"].isin(PEAK_HOURS).astype(int).values,
        best_alpha,
        best_floor,
        load_high_flag=load_high_test,
        spike_threshold=best_spike_threshold,
    )

    # 7）对照模型：线性回归与基线
    lr_model = LinearRegression()
    lr_model.fit(X_train_val, y_train_val)
    lr_pred_test = lr_model.predict(X_test)
    baseline_pred_24 = test_df["da_price_lag_24"].values if "da_price_lag_24" in test_df.columns else np.repeat(y_train_val.iloc[-1], len(y_test))
    baseline_pred_168 = test_df["da_price_lag_168"].values if "da_price_lag_168" in test_df.columns else np.repeat(np.nan, len(y_test))

    metrics_records = [
        evaluate_regression(y_test, baseline_pred_24, "基线模型_前24小时同小时"),
        evaluate_regression(y_test, baseline_pred_168, "基线模型_上周同时刻") if np.isfinite(baseline_pred_168).all() else {"模型":"基线模型_上周同时刻","MAE":np.nan,"RMSE":np.nan,"MAPE(%)":np.nan,"R2":np.nan},
        evaluate_regression(y_test, lr_pred_test, "线性回归"),
        evaluate_regression(y_test, base_pred_test, f"基础模型_{base_name}"),
        evaluate_regression(y_test, peak_pred_test, f"高峰专项模型_{peak_name}"),
        evaluate_regression(y_test, enhanced_pred_test, "高峰增强融合模型"),
    ]
    metrics_df = pd.DataFrame(metrics_records).drop_duplicates(subset=["模型"]).sort_values(["RMSE", "MAE", "MAPE(%)"]).reset_index(drop=True)

    # 8）高峰/尖刺专项评估
    test_peak_label, _ = build_peak_spike_label(test_df, y_test)
    peak_mask = test_df["hour"].isin(PEAK_HOURS).values
    spike_mask = test_peak_label.values.astype(bool)
    morning_mask = test_df["hour"].isin(MORNING_PEAK_HOURS).values

    compare_rows = []
    for name, pred in [
        (f"基础模型_{base_name}", base_pred_test),
        (f"高峰专项模型_{peak_name}", peak_pred_test),
        ("高峰增强融合模型", enhanced_pred_test),
    ]:
        overall = evaluate_regression(y_test, pred, name)
        peak_metric = subset_metrics(y_test[peak_mask], np.array(pred)[peak_mask], name)
        spike_metric = subset_metrics(y_test[spike_mask], np.array(pred)[spike_mask], name)
        morning_metric = subset_metrics(y_test[morning_mask], np.array(pred)[morning_mask], name)
        compare_rows.append({
            "模型": name,
            "整体RMSE": overall["RMSE"],
            "整体MAE": overall["MAE"],
            "高峰时段RMSE": peak_metric["RMSE"],
            "高峰时段MAE": peak_metric["MAE"],
            "晨峰RMSE": morning_metric["RMSE"],
            "晨峰MAE": morning_metric["MAE"],
            "尖峰样本RMSE": spike_metric["RMSE"],
            "尖峰样本MAE": spike_metric["MAE"],
        })
    peak_compare_df = pd.DataFrame(compare_rows)

    # 9）预测明细
    pred_result = test_df[["datetime", TARGET_COL, "hour"]].copy()
    pred_result.rename(columns={TARGET_COL: "真实值"}, inplace=True)
    pred_result["基线_前24小时同小时"] = baseline_pred_24
    if np.isfinite(baseline_pred_168).all():
        pred_result["基线_上周同一时刻"] = baseline_pred_168
    pred_result["线性回归预测值"] = lr_pred_test
    pred_result[f"基础模型_{base_name}预测值"] = base_pred_test
    pred_result[f"高峰专项模型_{peak_name}预测值"] = peak_pred_test
    pred_result["高峰增强融合预测值"] = enhanced_pred_test
    pred_result["raw_base_pred"] = base_pred_test
    pred_result["peak_pred"] = peak_pred_test
    pred_result["尖峰风险概率"] = risk_prob_test
    pred_result["spike_prob"] = risk_prob_test
    pred_result["融合权重"] = blend_weight_test
    pred_result["dynamic_alpha"] = blend_weight_test
    pred_result["blended_pred"] = enhanced_pred_test
    if np.isfinite(p90_pred_test).any():
        pred_result["p90_pred"] = p90_pred_test
    pred_result["预测误差"] = pred_result["高峰增强融合预测值"] - pred_result["真实值"]
    pred_result["绝对误差"] = np.abs(pred_result["预测误差"])

    # 10）验证结果汇总
    validation_summary = pd.DataFrame([
        {"项目": "基础模型", "值": base_name},
        {"项目": "高峰专项模型", "值": peak_name},
        {"项目": "尖峰分类器", "值": cls_name if cls_name is not None else "未启用"},
        {"项目": "最佳融合base_alpha", "值": best_alpha},
        {"项目": "最佳peak_floor", "值": best_floor},
        {"项目": "最佳尖峰分类阈值", "值": best_spike_threshold},
    ])

    artifacts = {
        "base_name": base_name,
        "peak_name": peak_name,
        "classifier_name": cls_name if cls_name is not None else "未启用",
        "best_alpha": best_alpha,
        "best_floor": best_floor,
        "best_spike_threshold": best_spike_threshold,
        "train_thresholds": train_thresholds,
        "base_validation_table": base_val_df,
        "peak_validation_table": peak_val_df,
        "classifier_validation_table": cls_val_df,
        "classifier_threshold_table": cls_threshold_df,
        "blend_search_table": blend_search_df,
        "validation_summary": validation_summary,
        "metrics_df": metrics_df,
        "peak_compare_df": peak_compare_df,
        "pred_result": pred_result,
        "feature_importance_df": get_feature_importance(final_base_model, feature_cols),
        "final_base_model": final_base_model,
        "final_peak_model": final_peak_model,
        "final_classifier": final_cls_model,
        "final_p90_model": final_p90_model,
        "base_pred_test": base_pred_test,
        "peak_pred_test": peak_pred_test,
        "enhanced_pred_test": enhanced_pred_test,
        "lr_pred_test": lr_pred_test,
    }
    return artifacts


def rolling_backtest_peak_enhanced(model_df: pd.DataFrame, feature_cols: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    backtest_metrics = []
    backtest_pred_list = []

    max_dt = model_df["datetime"].max()
    fold_days = ROLLING_BACKTEST_FOLD_DAYS

    for fold in range(ROLLING_BACKTEST_FOLDS, 0, -1):
        test_end = max_dt - pd.Timedelta(days=(fold - 1) * fold_days)
        test_start = test_end - pd.Timedelta(days=fold_days) + pd.Timedelta(hours=1)
        train_end = test_start - pd.Timedelta(hours=1)
        train_start = train_end - pd.Timedelta(days=MIN_TRAIN_DAYS_FOR_BACKTEST)

        full_train = model_df[(model_df["datetime"] >= train_start) & (model_df["datetime"] <= train_end)].copy()
        test_fold = model_df[(model_df["datetime"] >= test_start) & (model_df["datetime"] <= test_end)].copy()

        if len(full_train) < 24 * 90 or len(test_fold) < 24:
            continue

        inner_val_days = min(14, max(7, int(len(full_train) / 24 * 0.12)))
        inner_val_start = full_train["datetime"].max() - pd.Timedelta(days=inner_val_days) + pd.Timedelta(hours=1)
        train_fold = full_train[full_train["datetime"] < inner_val_start].copy()
        val_fold = full_train[full_train["datetime"] >= inner_val_start].copy()

        if len(train_fold) < 24 * 60 or len(val_fold) < 24 * 5:
            continue

        try:
            artifacts = run_peak_enhanced_pipeline(train_fold, val_fold, test_fold, feature_cols)
            y_test = test_fold[TARGET_COL].values
            pred = artifacts["enhanced_pred_test"]
            metrics = evaluate_regression(y_test, pred, f"高峰增强融合模型_fold_{ROLLING_BACKTEST_FOLDS - fold + 1}")
            metrics["Fold"] = ROLLING_BACKTEST_FOLDS - fold + 1
            metrics["训练开始"] = train_start
            metrics["训练结束"] = train_end
            metrics["测试开始"] = test_start
            metrics["测试结束"] = test_end
            backtest_metrics.append(metrics)

            fold_pred = pd.DataFrame({
                "Fold": metrics["Fold"],
                "datetime": test_fold["datetime"].values,
                "真实值": y_test,
                "预测值": pred,
                "预测误差": pred - y_test,
                "绝对误差": np.abs(pred - y_test),
            })
            backtest_pred_list.append(fold_pred)
        except Exception as e:
            log_print(f"滚动回测 Fold {ROLLING_BACKTEST_FOLDS - fold + 1} 失败，原因：{e}")

    metrics_df = pd.DataFrame(backtest_metrics)
    pred_df = pd.concat(backtest_pred_list, ignore_index=True) if backtest_pred_list else pd.DataFrame()
    return metrics_df, pred_df


# =========================
# 主流程
# =========================
def main() -> None:
    log_print("=" * 100)
    log_print("开始运行：高峰尖刺增强版 电力市场电价预测与智能分析系统")

    if not os.path.exists(MASTER_FILE):
        raise FileNotFoundError(f"未找到主表文件：{MASTER_FILE}")

    # 1. 读取数据
    log_print("开始读取主表数据...")
    df = pd.read_excel(MASTER_FILE)
    if "datetime" not in df.columns:
        raise ValueError("主表中未找到 datetime 字段，请检查文件结构。")

    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df_before = len(df)
    df = df.drop_duplicates(subset=["datetime"]).reset_index(drop=True)
    log_print(f"按 datetime 去重：{df_before} -> {len(df)}")

    # 2. 数据质量检查
    log_print("开始数据质量检查...")
    quality_rows = []
    for col in df.columns:
        quality_rows.append({
            "字段名": col,
            "数据类型": str(df[col].dtype),
            "缺失值数量": int(df[col].isna().sum()),
            "缺失率(%)": round(df[col].isna().mean() * 100, 6),
            "唯一值数量": int(df[col].nunique(dropna=True)),
        })
    quality_df = pd.DataFrame(quality_rows)
    quality_df.to_excel(os.path.join(TABLE_DIR, "01_数据质量检查.xlsx"), index=False)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    desc_df = df[numeric_cols].describe().T
    if TARGET_COL in desc_df.index:
        desc_df["偏度提示"] = ""
        desc_df.loc[TARGET_COL, "偏度提示"] = "若均值明显高于中位数，通常说明尖峰价格拉高整体均值"
    desc_df.to_excel(os.path.join(TABLE_DIR, "02_数值字段描述统计.xlsx"))

    # 3. 泄漏检查
    log_print("开始数据泄漏检查...")
    leak_report_df = leakage_check_report(df)
    leak_report_df.to_excel(os.path.join(TABLE_DIR, "03_数据泄漏检查报告.xlsx"), index=False)
    log_print(f"高风险/禁用字段数量：{int(leak_report_df['是否禁用'].sum())}")

    # 4. EDA 图表输出
    log_print("开始输出EDA图表...")
    fig = plt.figure(figsize=(16, 6))
    plt.plot(df["datetime"], df[TARGET_COL], linewidth=0.8)
    plt.title("DOM区域日前电价时间序列图")
    plt.xlabel("时间")
    plt.ylabel("日前电价（USD/MWh）")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "01_日前电价时间序列图.png"))

    if "actual_load" in df.columns:
        fig = plt.figure(figsize=(16, 6))
        plt.plot(df["datetime"], df["actual_load"], linewidth=0.8)
        plt.title("DOM区域实际负荷时间序列图")
        plt.xlabel("时间")
        plt.ylabel("实际负荷（MW）")
        plt.grid(alpha=0.3)
        save_fig(fig, os.path.join(FIG_DIR, "02_实际负荷时间序列图.png"))

    if "hour" not in df.columns:
        df = create_time_features(df, dt_col="datetime")

    hourly_mean = df.groupby("hour", as_index=False)[TARGET_COL].mean()
    fig = plt.figure(figsize=(10, 5))
    plt.plot(hourly_mean["hour"], hourly_mean[TARGET_COL], marker="o", linewidth=1)
    plt.title("按小时平均日前电价")
    plt.xlabel("小时")
    plt.ylabel("平均日前电价（USD/MWh）")
    plt.xticks(range(24))
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "03_按小时平均日前电价.png"))

    dow_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    dow_mean = df.groupby("day_of_week", as_index=False)[TARGET_COL].mean()
    dow_mean["星期"] = dow_mean["day_of_week"].map(dow_map)
    fig = plt.figure(figsize=(10, 5))
    plt.bar(dow_mean["星期"], dow_mean[TARGET_COL])
    plt.title("按星期平均日前电价")
    plt.xlabel("星期")
    plt.ylabel("平均日前电价（USD/MWh）")
    plt.grid(alpha=0.3, axis="y")
    save_fig(fig, os.path.join(FIG_DIR, "04_按星期平均日前电价.png"))

    monthly_mean = df.groupby(["year", "month"], as_index=False)[TARGET_COL].mean()
    monthly_mean["year_month"] = monthly_mean["year"].astype(str) + "-" + monthly_mean["month"].astype(str).str.zfill(2)
    fig = plt.figure(figsize=(16, 6))
    plt.plot(monthly_mean["year_month"], monthly_mean[TARGET_COL], marker="o", linewidth=1)
    plt.title("按月份平均日前电价")
    plt.xlabel("月份")
    plt.ylabel("平均日前电价（USD/MWh）")
    plt.xticks(rotation=60)
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "05_按月份平均日前电价.png"))

    daily_peak_valley = df.groupby(df["datetime"].dt.date).agg(日峰值=(TARGET_COL, "max"), 日谷值=(TARGET_COL, "min")).reset_index()
    daily_peak_valley["峰谷价差"] = daily_peak_valley["日峰值"] - daily_peak_valley["日谷值"]
    fig = plt.figure(figsize=(16, 6))
    plt.plot(pd.to_datetime(daily_peak_valley["datetime"]), daily_peak_valley["峰谷价差"], linewidth=0.8)
    plt.title("日前电价日峰谷价差趋势图")
    plt.xlabel("日期")
    plt.ylabel("峰谷价差（USD/MWh）")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "06_日前电价日峰谷价差趋势图.png"))

    if "actual_load" in df.columns:
        sample_df = df[["actual_load", TARGET_COL]].dropna().copy()
        if len(sample_df) > 5000:
            sample_df = sample_df.sample(5000, random_state=RANDOM_STATE)
        fig = plt.figure(figsize=(8, 6))
        plt.scatter(sample_df["actual_load"], sample_df[TARGET_COL], s=8, alpha=0.5)
        plt.title("实际负荷与日前电价关系散点图")
        plt.xlabel("实际负荷（MW）")
        plt.ylabel("日前电价（USD/MWh）")
        plt.grid(alpha=0.3)
        save_fig(fig, os.path.join(FIG_DIR, "07_实际负荷与日前电价关系散点图.png"))

    if "temperature" in df.columns:
        sample_df = df[["temperature", TARGET_COL]].dropna().copy()
        if len(sample_df) > 5000:
            sample_df = sample_df.sample(5000, random_state=RANDOM_STATE)
        fig = plt.figure(figsize=(8, 6))
        plt.scatter(sample_df["temperature"], sample_df[TARGET_COL], s=8, alpha=0.5)
        plt.title("温度与日前电价关系散点图")
        plt.xlabel("温度（℃）")
        plt.ylabel("日前电价（USD/MWh）")
        plt.grid(alpha=0.3)
        save_fig(fig, os.path.join(FIG_DIR, "08_温度与日前电价关系散点图.png"))

    pivot_table = df.pivot_table(values=TARGET_COL, index="day_of_week", columns="hour", aggfunc="mean")
    fig = plt.figure(figsize=(12, 6))
    plt.imshow(pivot_table, aspect="auto")
    plt.colorbar(label="平均日前电价（USD/MWh）")
    plt.title("星期-小时平均日前电价热力图")
    plt.xlabel("小时")
    plt.ylabel("星期（0=周一）")
    plt.xticks(range(24))
    plt.yticks(range(7))
    save_fig(fig, os.path.join(FIG_DIR, "09_星期_小时平均日前电价热力图.png"))

    # 5. 特征工程
    log_print("开始特征工程...")
    df = run_full_feature_engineering(df)

    feature_cols = build_feature_list(df)
    model_df = df[["datetime", TARGET_COL] + feature_cols].copy()
    model_df = model_df.dropna().reset_index(drop=True)
    model_df.to_excel(os.path.join(TABLE_DIR, "04_特征工程后建模表.xlsx"), index=False)
    log_print(f"建模样本量：{len(model_df)}，特征数量：{len(feature_cols)}")

    # 6. 时间切分：训练 / 验证 / 测试
    log_print("开始时间序列切分...")
    max_dt = model_df["datetime"].max()
    test_start_dt = max_dt - pd.Timedelta(days=TEST_DAYS) + pd.Timedelta(hours=1)
    val_start_dt = test_start_dt - pd.Timedelta(days=VAL_DAYS)

    train_df = model_df[model_df["datetime"] < val_start_dt].copy()
    val_df = model_df[(model_df["datetime"] >= val_start_dt) & (model_df["datetime"] < test_start_dt)].copy()
    test_df = model_df[model_df["datetime"] >= test_start_dt].copy()

    log_print(f"训练集：{train_df.shape}")
    log_print(f"验证集：{val_df.shape}")
    log_print(f"测试集：{test_df.shape}")
    log_print(f"验证开始时间：{val_start_dt}")
    log_print(f"测试开始时间：{test_start_dt}")

    # 7. 高峰尖刺增强建模管线
    log_print("开始执行高峰尖刺增强建模管线...")
    artifacts = run_peak_enhanced_pipeline(train_df, val_df, test_df, feature_cols)
    try:
        from prediction_engine.model_trainer import save_model_artifacts

        model_artifact_dir = save_model_artifacts(
            artifacts,
            feature_cols,
            train_df=train_df,
            val_df=val_df,
            test_df=test_df,
            run_id=os.environ.get("PIPELINE_RUN_ID"),
            extra_metadata={"engine": "v4_fix1_compat"},
        )
        log_print(f"模型 artifact 已保存：{model_artifact_dir}")
    except Exception as exc:
        log_print(f"模型 artifact 保存失败，不影响本次预测主流程：{exc}")

    # 8. 输出验证和模型结果
    artifacts["base_validation_table"].to_excel(os.path.join(TABLE_DIR, "05_候选模型验证集结果.xlsx"), index=False)
    artifacts["peak_validation_table"].to_excel(os.path.join(TABLE_DIR, "06_高峰专项模型验证结果.xlsx"), index=False)
    artifacts["classifier_validation_table"].to_excel(os.path.join(TABLE_DIR, "07_尖峰分类器验证结果.xlsx"), index=False)
    artifacts["blend_search_table"].to_excel(os.path.join(TABLE_DIR, "08_融合参数搜索结果.xlsx"), index=False)
    artifacts["validation_summary"].to_excel(os.path.join(TABLE_DIR, "09_高峰增强验证摘要.xlsx"), index=False)
    artifacts["metrics_df"].to_excel(os.path.join(TABLE_DIR, "10_模型评估结果.xlsx"), index=False)
    artifacts["peak_compare_df"].to_excel(os.path.join(TABLE_DIR, "11_高峰尖刺专项评估.xlsx"), index=False)
    artifacts["pred_result"].to_excel(os.path.join(TABLE_DIR, "12_测试集预测结果.xlsx"), index=False)
    artifacts["feature_importance_df"].to_excel(os.path.join(TABLE_DIR, "13_特征重要性.xlsx"), index=False)
    artifacts["base_validation_table"].to_excel(os.path.join(TABLE_DIR, "模型候选对比表.xlsx"), index=False)
    artifacts["peak_validation_table"].to_excel(os.path.join(TABLE_DIR, "高峰模型对比表.xlsx"), index=False)
    artifacts["classifier_validation_table"].to_excel(os.path.join(TABLE_DIR, "尖峰分类器对比表.xlsx"), index=False)
    if isinstance(artifacts.get("classifier_threshold_table"), pd.DataFrame) and not artifacts["classifier_threshold_table"].empty:
        artifacts["classifier_threshold_table"].to_excel(os.path.join(TABLE_DIR, "尖峰分类器阈值搜索表.xlsx"), index=False)

    log_print("测试集模型评估结果：")
    log_print(str(artifacts["metrics_df"]))
    log_print("高峰/尖刺专项评估：")
    log_print(str(artifacts["peak_compare_df"]))

    # 9. 图表输出
    pred_result = artifacts["pred_result"].copy()
    best_base_name = artifacts["base_name"]
    best_peak_name = artifacts["peak_name"]

    fig = plt.figure(figsize=(16, 6))
    plt.plot(pred_result["datetime"], pred_result["真实值"], label="真实值", linewidth=1)
    plt.plot(pred_result["datetime"], pred_result["高峰增强融合预测值"], label="高峰增强融合预测值", linewidth=1)
    plt.title("测试集真实值与高峰增强融合预测值对比图")
    plt.xlabel("时间")
    plt.ylabel("日前电价（USD/MWh）")
    plt.legend()
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "10_测试集真实值与高峰增强融合预测值对比图.png"))

    last_7d = pred_result[pred_result["datetime"] >= pred_result["datetime"].max() - pd.Timedelta(days=7)].copy()
    fig = plt.figure(figsize=(16, 6))
    plt.plot(last_7d["datetime"], last_7d["真实值"], label="真实值", linewidth=1.2)
    plt.plot(last_7d["datetime"], last_7d["高峰增强融合预测值"], label="高峰增强融合预测值", linewidth=1.2)
    plt.title("最后7天真实值与高峰增强融合预测值局部对比图")
    plt.xlabel("时间")
    plt.ylabel("日前电价（USD/MWh）")
    plt.legend()
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "11_最后7天局部预测对比图.png"))

    fig = plt.figure(figsize=(16, 6))
    plt.plot(pred_result["datetime"], pred_result["预测误差"], linewidth=0.8)
    plt.axhline(0, linestyle="--", linewidth=1)
    plt.title("高峰增强融合模型预测误差时间序列图")
    plt.xlabel("时间")
    plt.ylabel("预测误差")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "12_高峰增强融合模型预测误差时间序列图.png"))

    fig = plt.figure(figsize=(10, 6))
    plt.hist(np.abs(pred_result["预测误差"]), bins=50)
    plt.title("高峰增强融合模型绝对误差分布图")
    plt.xlabel("绝对误差")
    plt.ylabel("频数")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "13_高峰增强融合模型绝对误差分布图.png"))

    feature_importance_df = artifacts["feature_importance_df"]
    if not feature_importance_df.empty:
        top_n = min(TOP_N_FEATURES, len(feature_importance_df))
        top_df = feature_importance_df.head(top_n).iloc[::-1]
        fig = plt.figure(figsize=(10, 8))
        plt.barh(top_df["特征"], top_df["重要性"])
        plt.title(f"基础模型_{best_base_name}前{top_n}个特征重要性")
        plt.xlabel("重要性")
        plt.ylabel("特征")
        plt.grid(alpha=0.3, axis="x")
        save_fig(fig, os.path.join(FIG_DIR, "14_基础模型特征重要性图.png"))

    # 高峰专项对比图（晨峰重点）
    peak_compare_plot_df = pred_result[pred_result["hour"].isin(PEAK_HOURS)].copy()
    if len(peak_compare_plot_df) > 0:
        last_peak = peak_compare_plot_df[peak_compare_plot_df["datetime"] >= peak_compare_plot_df["datetime"].max() - pd.Timedelta(days=7)].copy()
        fig = plt.figure(figsize=(16, 6))
        plt.plot(last_peak["datetime"], last_peak["真实值"], label="真实值", linewidth=1.2)
        plt.plot(last_peak["datetime"], last_peak[f"基础模型_{best_base_name}预测值"], label=f"基础模型_{best_base_name}", linewidth=1.0)
        plt.plot(last_peak["datetime"], last_peak[f"高峰专项模型_{best_peak_name}预测值"], label=f"高峰专项模型_{best_peak_name}", linewidth=1.0)
        plt.plot(last_peak["datetime"], last_peak["高峰增强融合预测值"], label="高峰增强融合", linewidth=1.2)
        plt.title("最近7天高峰时段真实值与各模型预测对比图")
        plt.xlabel("时间")
        plt.ylabel("日前电价（USD/MWh）")
        plt.legend()
        plt.grid(alpha=0.3)
        save_fig(fig, os.path.join(FIG_DIR, "15_最近7天高峰时段真实值与各模型预测对比图.png"))

    # 10. 异常波动识别
    log_print("开始异常波动识别...")
    anomaly_df = identify_anomalies(pred_result[["datetime", "真实值", "高峰增强融合预测值", "预测误差"]].rename(columns={"高峰增强融合预测值": "预测值"}))
    anomaly_df.to_excel(os.path.join(TABLE_DIR, "14_异常波动明细.xlsx"), index=False)

    hourly_error_df = anomaly_df.copy()
    hourly_error_stat = hourly_error_df.groupby("hour", as_index=False).agg(
        小时样本量=("绝对误差", "size"),
        MAE=("绝对误差", "mean"),
        RMSE=("预测误差", lambda x: np.sqrt(np.mean(np.square(x)))),
        最大绝对误差=("绝对误差", "max"),
        异常点数量=("是否异常", "sum"),
    )
    hourly_error_stat.to_excel(os.path.join(TABLE_DIR, "15_按小时误差统计.xlsx"), index=False)
    diag_source = pred_result.copy()
    if {"真实值", "预测误差", "绝对误差"}.issubset(diag_source.columns) and len(diag_source) > 0:
        try:
            diag_source["价格分位段"] = pd.qcut(diag_source["真实值"], q=5, duplicates="drop")
            price_quantile_error = diag_source.groupby("价格分位段", observed=False).agg(
                样本量=("绝对误差", "size"),
                真实均价=("真实值", "mean"),
                MAE=("绝对误差", "mean"),
                RMSE=("预测误差", lambda x: np.sqrt(np.mean(np.square(x)))),
                bias_mean=("预测误差", "mean"),
                最大绝对误差=("绝对误差", "max"),
            ).reset_index()
            price_quantile_error["价格分位段"] = price_quantile_error["价格分位段"].astype(str)
        except Exception as exc:
            log_print(f"按价格分位数误差统计生成失败，改为空表：{exc}")
            price_quantile_error = pd.DataFrame()
        price_quantile_error.to_excel(os.path.join(TABLE_DIR, "按价格分位数误差统计.xlsx"), index=False)

        bias_rows = []
        for name, subset in [
            ("整体", diag_source),
            ("高峰时段", diag_source[diag_source["hour"].isin(PEAK_HOURS)] if "hour" in diag_source.columns else diag_source.iloc[0:0]),
            ("非高峰时段", diag_source[~diag_source["hour"].isin(PEAK_HOURS)] if "hour" in diag_source.columns else diag_source.iloc[0:0]),
        ]:
            if subset.empty:
                continue
            err = pd.to_numeric(subset["预测误差"], errors="coerce").dropna()
            abs_err = pd.to_numeric(subset["绝对误差"], errors="coerce").dropna()
            bias_rows.append({
                "分组": name,
                "样本量": int(len(subset)),
                "MAE": float(abs_err.mean()) if len(abs_err) else np.nan,
                "RMSE": float(np.sqrt(np.mean(np.square(err)))) if len(err) else np.nan,
                "bias_mean": float(err.mean()) if len(err) else np.nan,
                "bias_median": float(err.median()) if len(err) else np.nan,
                "高估次数": int((err > 0).sum()) if len(err) else 0,
                "低估次数": int((err < 0).sum()) if len(err) else 0,
                "高估比例": float((err > 0).mean()) if len(err) else np.nan,
                "低估比例": float((err < 0).mean()) if len(err) else np.nan,
            })
        pd.DataFrame(bias_rows).to_excel(os.path.join(TABLE_DIR, "预测偏差诊断.xlsx"), index=False)

    fig = plt.figure(figsize=(12, 5))
    plt.bar(hourly_error_stat["hour"], hourly_error_stat["MAE"])
    plt.title("测试集按小时平均绝对误差（MAE）")
    plt.xlabel("小时")
    plt.ylabel("MAE")
    plt.xticks(range(24))
    plt.grid(alpha=0.3, axis="y")
    save_fig(fig, os.path.join(FIG_DIR, "16_测试集按小时平均绝对误差图.png"))

    anomaly_points = anomaly_df[anomaly_df["是否异常"] == 1].copy()
    fig = plt.figure(figsize=(16, 6))
    plt.plot(anomaly_df["datetime"], anomaly_df["真实值"], label="真实值", linewidth=1)
    plt.plot(anomaly_df["datetime"], anomaly_df["预测值"], label="预测值", linewidth=1)
    if len(anomaly_points) > 0:
        plt.scatter(anomaly_points["datetime"], anomaly_points["真实值"], label="异常点", s=40)
    plt.title("测试集异常波动识别图")
    plt.xlabel("时间")
    plt.ylabel("日前电价（USD/MWh）")
    plt.legend()
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "17_测试集异常波动识别图.png"))

    if len(anomaly_df) > 0:
        top_anomaly = anomaly_df.head(min(20, len(anomaly_df))).copy().iloc[::-1]
        fig = plt.figure(figsize=(10, 8))
        plt.barh(top_anomaly["datetime"].astype(str), top_anomaly["绝对误差"])
        plt.title("Top20异常波动时点绝对误差")
        plt.xlabel("绝对误差")
        plt.ylabel("时间")
        plt.grid(alpha=0.3, axis="x")
        save_fig(fig, os.path.join(FIG_DIR, "18_Top20异常波动时点绝对误差图.png"))

    # 11. 滚动回测
    if ENABLE_ROLLING_BACKTEST:
        log_print("开始滚动回测...")
        backtest_metrics_df, backtest_pred_df = rolling_backtest_peak_enhanced(model_df, feature_cols)
        backtest_metrics_df.to_excel(os.path.join(TABLE_DIR, "16_滚动回测结果.xlsx"), index=False)
        if not backtest_pred_df.empty:
            backtest_pred_df.to_excel(os.path.join(TABLE_DIR, "17_滚动回测预测明细.xlsx"), index=False)

        if not backtest_metrics_df.empty:
            fig = plt.figure(figsize=(10, 5))
            plt.plot(backtest_metrics_df["Fold"], backtest_metrics_df["RMSE"], marker="o")
            plt.title("滚动回测各Fold的RMSE")
            plt.xlabel("Fold")
            plt.ylabel("RMSE")
            plt.grid(alpha=0.3)
            save_fig(fig, os.path.join(FIG_DIR, "19_滚动回测各Fold的RMSE.png"))

            fig = plt.figure(figsize=(10, 5))
            plt.plot(backtest_metrics_df["Fold"], backtest_metrics_df["MAPE(%)"], marker="o")
            plt.title("滚动回测各Fold的MAPE")
            plt.xlabel("Fold")
            plt.ylabel("MAPE(%)")
            plt.grid(alpha=0.3)
            save_fig(fig, os.path.join(FIG_DIR, "20_滚动回测各Fold的MAPE.png"))
    else:
        log_print("根据环境变量 ENABLE_ROLLING_BACKTEST=0，跳过滚动回测。")

    # 12. 未来24小时预测（正式前瞻版）
    log_print("开始生成未来24小时预测结果（正式前瞻版）...")
    future_result, future_feature_snapshot = generate_formal_forward_forecast(df, feature_cols, artifacts, model_df)
    try:
        from prediction_engine.formal_forecast import add_residual_prediction_intervals

        future_result = add_residual_prediction_intervals(future_result, artifacts.get("pred_result"))
        log_print("未来24小时正式预测已增加残差分布 P10/P90 预测区间。")
    except Exception as exc:
        log_print(f"预测区间生成失败，保留原点预测结果：{exc}")
    future_result.to_excel(os.path.join(TABLE_DIR, "18_未来24小时预测结果_正式版.xlsx"), index=False)
    future_feature_snapshot.to_excel(os.path.join(TABLE_DIR, "18_未来24小时预测输入特征_正式版.xlsx"), index=False)

    weather_source_text = "、".join(sorted([str(x) for x in future_result["future_weather_source"].dropna().unique().tolist() if str(x).strip()]))
    log_print(f"未来24小时正式版预测时间范围：{future_result['datetime'].min()} -> {future_result['datetime'].max()}")
    log_print(f"未来24小时天气来源：{weather_source_text or '未知'}")
    log_print(f"未来24小时预测缺失特征填补总数：{int(future_result['缺失特征填补数量'].sum())}")

    fig = plt.figure(figsize=(12, 6))
    plt.plot(future_result["datetime"], future_result["预测的未来24小时日前电价"], marker="o", linewidth=1)
    plt.title("未来24小时日前电价预测结果（正式前瞻版）")
    plt.xlabel("时间")
    plt.ylabel("预测电价（USD/MWh）")
    plt.xticks(rotation=45)
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "21_未来24小时日前电价预测图_正式版.png"))

    # 13. 业务统计摘要
    log_print("开始输出业务统计结果...")
    main_metrics = artifacts["metrics_df"].copy()
    if "高峰增强融合模型" in main_metrics["模型"].values:
        best_row = main_metrics[main_metrics["模型"] == "高峰增强融合模型"].iloc[0]
    else:
        best_row = main_metrics.iloc[0]

    business_summary = [
        {"指标": "样本总量", "值": len(df)},
        {"指标": "起始时间", "值": str(df["datetime"].min())},
        {"指标": "结束时间", "值": str(df["datetime"].max())},
        {"指标": "平均日前电价", "值": round(df[TARGET_COL].mean(), 4)},
        {"指标": "日前电价最大值", "值": round(df[TARGET_COL].max(), 4)},
        {"指标": "日前电价最小值", "值": round(df[TARGET_COL].min(), 4)},
        {"指标": "平均实际负荷", "值": round(df["actual_load"].mean(), 4) if "actual_load" in df.columns else ""},
        {"指标": "最大实际负荷", "值": round(df["actual_load"].max(), 4) if "actual_load" in df.columns else ""},
        {"指标": "平均预测负荷", "值": round(df["forecast_load"].mean(), 4) if "forecast_load" in df.columns else ""},
        {"指标": "平均温度", "值": round(df["temperature"].mean(), 4) if "temperature" in df.columns else ""},
        {"指标": "测试集主模型", "值": "高峰增强融合模型"},
        {"指标": "测试集MAE", "值": round(float(best_row["MAE"]), 6)},
        {"指标": "测试集RMSE", "值": round(float(best_row["RMSE"]), 6)},
        {"指标": "测试集MAPE(%)", "值": round(float(best_row["MAPE(%)"]), 6)},
        {"指标": "测试集R2", "值": round(float(best_row["R2"]), 6)},
        {"指标": "高峰专项基础模型", "值": artifacts["base_name"]},
        {"指标": "高峰专项模型", "值": artifacts["peak_name"]},
        {"指标": "尖峰风险分类器", "值": artifacts["classifier_name"]},
        {"指标": "最佳融合alpha", "值": artifacts["best_alpha"]},
        {"指标": "最佳peak_floor", "值": artifacts["best_floor"]},
        {"指标": "异常点数量", "值": int(anomaly_df["是否异常"].sum())},
        {"指标": "测试集异常点占比(%)", "值": round(float(anomaly_df["是否异常"].mean() * 100), 6)},
        {"指标": "未来24小时预测口径", "值": "正式前瞻版"},
        {"指标": "未来24小时预测开始", "值": str(future_result["datetime"].min())},
        {"指标": "未来24小时预测结束", "值": str(future_result["datetime"].max())},
        {"指标": "未来24小时天气来源", "值": weather_source_text},
    ]
    business_summary_df = pd.DataFrame(business_summary)
    business_summary_df.to_excel(os.path.join(TABLE_DIR, "19_业务统计摘要.xlsx"), index=False)

    # 14. README
    readme_text = f"""
    项目运行完成。

    一、输入文件
    - 主表路径：{MASTER_FILE}

    二、输出目录
    - 图表目录：{FIG_DIR}
    - 结果表目录：{TABLE_DIR}
    - 日志目录：{LOG_DIR}

    三、本次新增重点
    1. 严格去泄漏建模
    2. 高峰尖刺专项模型
    3. 尖峰风险分类器
    4. 融合参数自动搜索
    5. 高峰/尖峰专项评估
    6. 滚动回测

    四、最终主模型
    - 基础模型：{artifacts['base_name']}
    - 高峰专项模型：{artifacts['peak_name']}
    - 尖峰分类器：{artifacts['classifier_name']}
    - 最终输出：高峰增强融合模型
    - 最佳 alpha：{artifacts['best_alpha']}
    - 最佳 peak_floor：{artifacts['best_floor']}

    五、未来24小时正式预测
    - 预测口径：正式前瞻版（递推预测）
    - 预测开始：{future_result["datetime"].min()}
    - 预测结束：{future_result["datetime"].max()}
    - 天气来源：{weather_source_text or "历史滞后天气代理"}

    六、下一步建议
    1）若任务计划每天先更新数据，再运行本脚本，可把正式前瞻预测时点推到最新交易日；
    2）可进一步做晨峰（6-9点）单独模型与多任务建模；
    3）可增加分位数回归或误差区间预测，增强对尖峰价的风险提示。
    """
    with open(os.path.join(RESULT_DIR, "README_结果说明_高峰尖刺增强版.txt"), "w", encoding="utf-8") as f:
        f.write(readme_text)

    log_print("=" * 100)
    log_print("全部运行完成！")
    log_print(f"图表输出目录：{FIG_DIR}")
    log_print(f"结果表输出目录：{TABLE_DIR}")
    log_print(f"日志输出目录：{LOG_DIR}")


if __name__ == "__main__":
    main()
