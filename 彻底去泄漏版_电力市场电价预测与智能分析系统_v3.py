# -*- coding: utf-8 -*-
"""
项目名称：基于公开电力市场数据的电价预测与智能分析系统
当前版本：彻底去泄漏版（保留原核心功能 + 泄漏检查 + 严格时序特征约束）

核心改动说明：
1）保留原有核心功能：数据读取、数据质量检查、EDA、特征工程、模型评估、预测结果输出、图表输出；
2）新增“数据泄漏检查报告”，明确标记高风险字段与禁用字段；
3）彻底移除目标泄漏与后验信息泄漏：
   - 不再把当前时点 da_price 派生量作为特征输入；
   - 不再把当前时点 actual_load、rt_price、rt相关派生量作为特征输入；
   - 不再把依赖当前时点 actual_load 的 load_gap / load_ratio 作为特征输入；
4）价格变化特征仅允许基于历史滞后值构造；
5）滚动/分组历史特征全部基于 shift(1) 或更早时点构造；
6）保留异常波动识别、滚动回测、多模型对比与未来24小时演示版输出；
7）全部结果保存到指定目录。
"""

import os
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
RESULT_DIR = r"E:\智能运营分析项目\结果-2"
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
ANOMALY_MIN_ABS_ERROR = 30.0
TOP_N_FEATURES = 25
TARGET_COL = "da_price"

# 明确禁用的泄漏/后验字段（严格未来24小时预测不可直接使用）
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
        "R2": r2
    }


def expanding_group_mean(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding().mean()


def expanding_group_std(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding().std()


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
        "forecast_load": [1, 2, 24, 25, 48, 168],
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

    # 天气相关：只构造历史滞后基础上的派生项，不直接把当前时点观测天气作为未来输入
    if "temperature_lag_1" in df.columns:
        df["temperature_lag_1_sq"] = df["temperature_lag_1"] ** 2
        df["cooling_degree_lag_1"] = np.maximum(df["temperature_lag_1"] - 22, 0)
        df["heating_degree_lag_1"] = np.maximum(18 - df["temperature_lag_1"], 0)
    if "temperature_lag_24" in df.columns and "temperature_lag_48" in df.columns:
        df["temp_hist_change_24h"] = df["temperature_lag_24"] - df["temperature_lag_48"]
    if "temperature_lag_1" in df.columns and "temperature_lag_2" in df.columns:
        df["temp_hist_change_1h"] = df["temperature_lag_1"] - df["temperature_lag_2"]

    # 负荷相关：forecast_load_t 可用；actual_load_t 不可用，只允许其滞后值
    if "forecast_load" in df.columns:
        if "forecast_load_lag_1" in df.columns:
            df["forecast_load_change_1h_safe"] = df["forecast_load"] - df["forecast_load_lag_1"]
        if "forecast_load_lag_24" in df.columns:
            df["forecast_load_change_24h_safe"] = df["forecast_load"] - df["forecast_load_lag_24"]
    if "actual_load_lag_1" in df.columns and "actual_load_lag_2" in df.columns:
        df["actual_load_hist_change_1h"] = df["actual_load_lag_1"] - df["actual_load_lag_2"]
    if "actual_load_lag_24" in df.columns and "actual_load_lag_48" in df.columns:
        df["actual_load_hist_change_24h"] = df["actual_load_lag_24"] - df["actual_load_lag_48"]

    # 价格相关：只允许基于滞后值构造历史变化，不允许把当前 da_price 直接揉进特征
    if "da_price_lag_1" in df.columns and "da_price_lag_2" in df.columns:
        df["price_hist_change_1h"] = df["da_price_lag_1"] - df["da_price_lag_2"]
        df["price_hist_ratio_1h"] = df["da_price_lag_1"] / np.where(np.abs(df["da_price_lag_2"]) < 1e-6, 1e-6, df["da_price_lag_2"])
    if "da_price_lag_24" in df.columns and "da_price_lag_48" in df.columns:
        df["price_hist_change_24h"] = df["da_price_lag_24"] - df["da_price_lag_48"]
        df["price_hist_ratio_24h"] = df["da_price_lag_24"] / np.where(np.abs(df["da_price_lag_48"]) < 1e-6, 1e-6, df["da_price_lag_48"])

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
        df["is_peak_hour"] = df["hour"].isin([6, 7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)
        df["is_valley_hour"] = df["hour"].isin([0, 1, 2, 3, 4, 5]).astype(int)

    return df


def leakage_check_report(df: pd.DataFrame) -> pd.DataFrame:
    """输出泄漏检查报告。"""
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
            "说明": reason
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
        "is_peak_hour", "is_valley_hour",
        "forecast_load_change_1h_safe", "forecast_load_change_24h_safe",

        # 历史统计特征
        "da_price_hist_hour_mean", "da_price_hist_hour_std",
        "da_price_hist_dow_mean", "da_price_hist_month_mean", "da_price_hist_weekend_mean",

        # 历史价格滞后
        "da_price_lag_1", "da_price_lag_2", "da_price_lag_3", "da_price_lag_6", "da_price_lag_12",
        "da_price_lag_18", "da_price_lag_24", "da_price_lag_25", "da_price_lag_48",
        "da_price_lag_72", "da_price_lag_96", "da_price_lag_168", "da_price_lag_169",

        # 严格历史价格变化特征
        "price_hist_change_1h", "price_hist_change_24h", "price_hist_ratio_1h", "price_hist_ratio_24h",
        "price_spread_rt_minus_da_lag_1", "price_spread_rt_minus_da_lag_24", "price_spread_rt_minus_da_lag_168",

        # 负荷滞后
        "forecast_load_lag_1", "forecast_load_lag_2", "forecast_load_lag_24",
        "forecast_load_lag_25", "forecast_load_lag_48", "forecast_load_lag_168",
        "actual_load_lag_1", "actual_load_lag_2", "actual_load_lag_24",
        "actual_load_lag_25", "actual_load_lag_48", "actual_load_lag_168",
        "actual_load_hist_change_1h", "actual_load_hist_change_24h",

        # 天气滞后（不用当前时点观测值）
        "temperature_lag_1", "temperature_lag_2", "temperature_lag_24", "temperature_lag_48", "temperature_lag_168",
        "wind_speed_lag_1", "wind_speed_lag_24", "wind_speed_lag_48",
        "precipitation_lag_1", "precipitation_lag_24", "precipitation_lag_48",
        "temperature_lag_1_sq", "cooling_degree_lag_1", "heating_degree_lag_1",
        "temp_hist_change_1h", "temp_hist_change_24h",

        # 滚动统计（全部基于 shift 后构造）
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

        # EWM（全部基于 shift 后构造）
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


# =========================
# 模型
# =========================
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
                objective="reg:squarederror",
                random_state=RANDOM_STATE,
                n_jobs=-1,
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
                random_state=RANDOM_STATE,
                verbose=-1,
            )
        })

    candidates.extend([
        {
            "name": "HistGB_raw",
            "use_log_target": False,
            "builder": lambda: HistGradientBoostingRegressor(
                learning_rate=0.05,
                max_depth=8,
                max_iter=500,
                random_state=RANDOM_STATE,
            )
        },
        {
            "name": "RandomForest_raw",
            "use_log_target": False,
            "builder": lambda: RandomForestRegressor(
                n_estimators=500,
                max_depth=18,
                min_samples_split=4,
                min_samples_leaf=2,
                random_state=RANDOM_STATE,
                n_jobs=-1,
            )
        },
        {
            "name": "线性回归",
            "use_log_target": False,
            "builder": lambda: LinearRegression()
        }
    ])
    return candidates


def fit_and_predict(model_info: Dict, X_train, y_train, X_valid):
    model = model_info["builder"]()
    if model_info["use_log_target"]:
        y_train_fit = np.log1p(np.clip(y_train, a_min=0, a_max=None))
        model.fit(X_train, y_train_fit)
        pred = np.expm1(model.predict(X_valid))
    else:
        model.fit(X_train, y_train)
        pred = model.predict(X_valid)
    return model, pred


def select_best_model(X_train, y_train, X_valid, y_valid):
    records = []
    fitted_models = {}

    for model_info in get_model_candidates():
        model_name = model_info["name"]
        try:
            model, pred = fit_and_predict(model_info, X_train, y_train, X_valid)
            metrics = evaluate_regression(y_valid, pred, model_name)
            records.append(metrics)
            fitted_models[model_name] = model
            log_print(f"候选模型 {model_name} 验证完成：RMSE={metrics['RMSE']:.6f}, MAPE={metrics['MAPE(%)']:.6f}%")
        except Exception as e:
            log_print(f"候选模型 {model_name} 运行失败，原因：{e}")

    result_df = pd.DataFrame(records).sort_values(["RMSE", "MAE", "MAPE(%)"]).reset_index(drop=True)
    if result_df.empty:
        raise RuntimeError("所有候选模型均失败，请检查环境或数据。")

    best_model_name = result_df.loc[0, "模型"]
    best_model = fitted_models[best_model_name]
    return best_model_name, best_model, result_df


def get_feature_importance(model, feature_names: List[str]) -> pd.DataFrame:
    if hasattr(model, "feature_importances_"):
        imp = pd.DataFrame({
            "特征": feature_names,
            "重要性": model.feature_importances_
        }).sort_values("重要性", ascending=False)
        return imp
    elif hasattr(model, "coef_"):
        coef = np.ravel(np.array(model.coef_))
        imp = pd.DataFrame({
            "特征": feature_names,
            "重要性": np.abs(coef)
        }).sort_values("重要性", ascending=False)
        return imp
    else:
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

    if "datetime" in pred_df.columns:
        pred_df["hour"] = pd.to_datetime(pred_df["datetime"]).dt.hour
        pred_df["是否高峰时段"] = pred_df["hour"].isin([6, 7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)
    else:
        pred_df["是否高峰时段"] = 0

    return pred_df.sort_values("绝对误差", ascending=False)


def rolling_backtest(model_name: str, feature_cols: List[str], model_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    backtest_metrics = []
    backtest_pred_list = []

    max_dt = model_df["datetime"].max()
    fold_days = ROLLING_BACKTEST_FOLD_DAYS

    for fold in range(ROLLING_BACKTEST_FOLDS, 0, -1):
        test_end = max_dt - pd.Timedelta(days=(fold - 1) * fold_days)
        test_start = test_end - pd.Timedelta(days=fold_days) + pd.Timedelta(hours=1)
        train_end = test_start - pd.Timedelta(hours=1)
        train_start = train_end - pd.Timedelta(days=MIN_TRAIN_DAYS_FOR_BACKTEST)

        train_fold = model_df[(model_df["datetime"] >= train_start) & (model_df["datetime"] <= train_end)].copy()
        test_fold = model_df[(model_df["datetime"] >= test_start) & (model_df["datetime"] <= test_end)].copy()

        if len(train_fold) < 24 * 60 or len(test_fold) < 24:
            continue

        X_train = train_fold[feature_cols]
        y_train = train_fold[TARGET_COL]
        X_test = test_fold[feature_cols]
        y_test = test_fold[TARGET_COL]

        model_builder = None
        for item in get_model_candidates():
            if item["name"] == model_name:
                model_builder = item
                break
        if model_builder is None:
            model_builder = {
                "name": "RandomForest_raw",
                "use_log_target": False,
                "builder": lambda: RandomForestRegressor(
                    n_estimators=500,
                    max_depth=18,
                    min_samples_split=4,
                    min_samples_leaf=2,
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                )
            }

        model, pred = fit_and_predict(model_builder, X_train, y_train, X_test)
        metrics = evaluate_regression(y_test, pred, f"{model_name}_fold_{ROLLING_BACKTEST_FOLDS - fold + 1}")
        metrics["Fold"] = ROLLING_BACKTEST_FOLDS - fold + 1
        metrics["训练开始"] = train_start
        metrics["训练结束"] = train_end
        metrics["测试开始"] = test_start
        metrics["测试结束"] = test_end
        backtest_metrics.append(metrics)

        fold_pred = pd.DataFrame({
            "Fold": metrics["Fold"],
            "datetime": test_fold["datetime"].values,
            "真实值": y_test.values,
            "预测值": pred,
            "预测误差": pred - y_test.values,
            "绝对误差": np.abs(pred - y_test.values),
        })
        backtest_pred_list.append(fold_pred)

    metrics_df = pd.DataFrame(backtest_metrics)
    pred_df = pd.concat(backtest_pred_list, ignore_index=True) if backtest_pred_list else pd.DataFrame()
    return metrics_df, pred_df


# =========================
# 主流程
# =========================
log_print("=" * 100)
log_print("开始运行：彻底去泄漏版 电力市场电价预测与智能分析系统")

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
        "唯一值数量": int(df[col].nunique(dropna=True))
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

# 先构造时间字段用于EDA
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
df = create_time_features(df, dt_col="datetime")
df = create_lag_features(df)
df = create_rolling_features(df)
df = create_ewm_features(df)
df = create_history_group_features(df)
df = add_safe_business_features(df)

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

X_train = train_df[feature_cols]
y_train = train_df[TARGET_COL]
X_val = val_df[feature_cols]
y_val = val_df[TARGET_COL]
X_test = test_df[feature_cols]
y_test = test_df[TARGET_COL]

# 7. 基线模型
log_print("开始训练基线模型...")
metrics_list = []

baseline_pred_24 = test_df["da_price_lag_24"].values if "da_price_lag_24" in test_df.columns else np.repeat(y_train.iloc[-1], len(y_test))
metrics_list.append(evaluate_regression(y_test, baseline_pred_24, "基线模型_前24小时同小时"))

if "da_price_lag_168" in test_df.columns:
    baseline_pred_168 = test_df["da_price_lag_168"].values
    metrics_list.append(evaluate_regression(y_test, baseline_pred_168, "基线模型_上周同时刻"))
else:
    baseline_pred_168 = np.repeat(np.nan, len(y_test))

# 8. 候选模型选择
log_print("开始候选模型验证...")
best_model_name, _, val_result_df = select_best_model(X_train, y_train, X_val, y_val)
val_result_df.to_excel(os.path.join(TABLE_DIR, "05_候选模型验证集结果.xlsx"), index=False)
log_print(f"验证集最佳模型：{best_model_name}")

# 9. 用训练+验证重新拟合最佳模型并测试
log_print("开始在训练+验证集上重训最佳模型...")
train_val_df = pd.concat([train_df, val_df], axis=0).reset_index(drop=True)
X_train_val = train_val_df[feature_cols]
y_train_val = train_val_df[TARGET_COL]

best_model_info = None
for item in get_model_candidates():
    if item["name"] == best_model_name:
        best_model_info = item
        break
if best_model_info is None:
    raise RuntimeError("未找到最佳模型配置。")

best_model, test_pred = fit_and_predict(best_model_info, X_train_val, y_train_val, X_test)
metrics_list.append(evaluate_regression(y_test, test_pred, best_model_name))

# 额外保留线性回归对照，但现在应不再完美拟合
lr_model = LinearRegression()
lr_model.fit(X_train_val, y_train_val)
lr_pred = lr_model.predict(X_test)
metrics_list.append(evaluate_regression(y_test, lr_pred, "线性回归"))

metrics_df = pd.DataFrame(metrics_list).drop_duplicates(subset=["模型"]).sort_values(["RMSE", "MAE", "MAPE(%)"]).reset_index(drop=True)
metrics_df.to_excel(os.path.join(TABLE_DIR, "06_模型评估结果.xlsx"), index=False)
log_print("测试集模型评估结果：")
log_print(str(metrics_df))

# 10. 测试集预测结果
pred_result = test_df[["datetime", TARGET_COL]].copy()
pred_result.rename(columns={TARGET_COL: "真实值"}, inplace=True)
pred_result["基线_前24小时同小时"] = baseline_pred_24
if len(baseline_pred_168) == len(pred_result):
    pred_result["基线_上周同一时刻"] = baseline_pred_168
pred_result[f"{best_model_name}预测值"] = test_pred
pred_result["线性回归预测值"] = lr_pred
pred_result["预测误差"] = pred_result[f"{best_model_name}预测值"] - pred_result["真实值"]
pred_result["绝对误差"] = np.abs(pred_result["预测误差"])
pred_result.to_excel(os.path.join(TABLE_DIR, "07_测试集预测结果.xlsx"), index=False)

# 11. 特征重要性
feature_importance_df = get_feature_importance(best_model, feature_cols)
feature_importance_df.to_excel(os.path.join(TABLE_DIR, "08_特征重要性.xlsx"), index=False)

if not feature_importance_df.empty:
    top_n = min(TOP_N_FEATURES, len(feature_importance_df))
    top_df = feature_importance_df.head(top_n).iloc[::-1]
    fig = plt.figure(figsize=(10, 8))
    plt.barh(top_df["特征"], top_df["重要性"])
    plt.title(f"{best_model_name}前{top_n}个特征重要性")
    plt.xlabel("重要性")
    plt.ylabel("特征")
    plt.grid(alpha=0.3, axis="x")
    save_fig(fig, os.path.join(FIG_DIR, "10_主模型特征重要性图.png"))

# 12. 预测图
fig = plt.figure(figsize=(16, 6))
plt.plot(pred_result["datetime"], pred_result["真实值"], label="真实值", linewidth=1)
plt.plot(pred_result["datetime"], pred_result[f"{best_model_name}预测值"], label=f"{best_model_name}预测值", linewidth=1)
plt.title(f"测试集真实值与{best_model_name}预测值对比图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.legend()
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "11_测试集真实值与主模型预测值对比图.png"))

last_7d = pred_result[pred_result["datetime"] >= pred_result["datetime"].max() - pd.Timedelta(days=7)].copy()
fig = plt.figure(figsize=(16, 6))
plt.plot(last_7d["datetime"], last_7d["真实值"], label="真实值", linewidth=1.2)
plt.plot(last_7d["datetime"], last_7d[f"{best_model_name}预测值"], label=f"{best_model_name}预测值", linewidth=1.2)
plt.title("最后7天真实值与主模型预测值局部对比图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.legend()
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "12_最后7天局部预测对比图.png"))

fig = plt.figure(figsize=(16, 6))
plt.plot(pred_result["datetime"], pred_result["预测误差"], linewidth=0.8)
plt.axhline(0, linestyle="--", linewidth=1)
plt.title(f"{best_model_name}预测误差时间序列图")
plt.xlabel("时间")
plt.ylabel("预测误差")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "13_主模型预测误差时间序列图.png"))

fig = plt.figure(figsize=(10, 6))
plt.hist(pred_result["绝对误差"], bins=50)
plt.title(f"{best_model_name}绝对误差分布图")
plt.xlabel("绝对误差")
plt.ylabel("频数")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "14_主模型绝对误差分布图.png"))

# 13. 异常波动识别
log_print("开始异常波动识别...")
anomaly_df = identify_anomalies(pred_result)
anomaly_df.to_excel(os.path.join(TABLE_DIR, "09_异常波动明细.xlsx"), index=False)

hourly_error_df = anomaly_df.copy()
hourly_error_df["hour"] = pd.to_datetime(hourly_error_df["datetime"]).dt.hour
hourly_error_stat = hourly_error_df.groupby("hour", as_index=False).agg(
    小时样本量=("绝对误差", "size"),
    MAE=("绝对误差", "mean"),
    RMSE=("预测误差", lambda x: np.sqrt(np.mean(np.square(x)))),
    最大绝对误差=("绝对误差", "max"),
    异常点数量=("是否异常", "sum")
)
hourly_error_stat.to_excel(os.path.join(TABLE_DIR, "10_按小时误差统计.xlsx"), index=False)

fig = plt.figure(figsize=(12, 5))
plt.bar(hourly_error_stat["hour"], hourly_error_stat["MAE"])
plt.title("测试集按小时平均绝对误差（MAE）")
plt.xlabel("小时")
plt.ylabel("MAE")
plt.xticks(range(24))
plt.grid(alpha=0.3, axis="y")
save_fig(fig, os.path.join(FIG_DIR, "15_测试集按小时平均绝对误差图.png"))

anomaly_points = anomaly_df[anomaly_df["是否异常"] == 1].copy()
fig = plt.figure(figsize=(16, 6))
plt.plot(anomaly_df["datetime"], anomaly_df["真实值"], label="真实值", linewidth=1)
plt.plot(anomaly_df["datetime"], anomaly_df[f"{best_model_name}预测值"], label="预测值", linewidth=1)
if len(anomaly_points) > 0:
    plt.scatter(anomaly_points["datetime"], anomaly_points["真实值"], label="异常点", s=40)
plt.title("测试集异常波动识别图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.legend()
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "16_测试集异常波动识别图.png"))

if len(anomaly_df) > 0:
    top_anomaly = anomaly_df.head(min(20, len(anomaly_df))).copy().iloc[::-1]
    fig = plt.figure(figsize=(10, 8))
    plt.barh(top_anomaly["datetime"].astype(str), top_anomaly["绝对误差"])
    plt.title("Top20异常波动时点绝对误差")
    plt.xlabel("绝对误差")
    plt.ylabel("时间")
    plt.grid(alpha=0.3, axis="x")
    save_fig(fig, os.path.join(FIG_DIR, "17_Top20异常波动时点绝对误差图.png"))

# 14. 滚动回测
log_print("开始滚动回测...")
backtest_metrics_df, backtest_pred_df = rolling_backtest(best_model_name, feature_cols, model_df)
backtest_metrics_df.to_excel(os.path.join(TABLE_DIR, "11_滚动回测结果.xlsx"), index=False)
if not backtest_pred_df.empty:
    backtest_pred_df.to_excel(os.path.join(TABLE_DIR, "12_滚动回测预测明细.xlsx"), index=False)

if not backtest_metrics_df.empty:
    fig = plt.figure(figsize=(10, 5))
    plt.plot(backtest_metrics_df["Fold"], backtest_metrics_df["RMSE"], marker="o", linewidth=1)
    plt.title("滚动回测RMSE变化图")
    plt.xlabel("Fold")
    plt.ylabel("RMSE")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "18_滚动回测RMSE变化图.png"))

    fig = plt.figure(figsize=(10, 5))
    plt.plot(backtest_metrics_df["Fold"], backtest_metrics_df["MAPE(%)"], marker="o", linewidth=1)
    plt.title("滚动回测MAPE变化图")
    plt.xlabel("Fold")
    plt.ylabel("MAPE(%)")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "19_滚动回测MAPE变化图.png"))

# 15. 未来24小时预测（演示版）
# 说明：若无未来天气预报和未来新发布负荷预测，本模块仅作为“按最新特征快照进行演示”输出。
log_print("开始生成未来24小时预测结果（演示版）...")
future_24 = model_df.tail(24).copy()
future_24_features = future_24[["datetime"] + feature_cols].copy()
future_24_features["预测的未来24小时日前电价"] = best_model.predict(future_24_features[feature_cols])
future_24_result = future_24_features[["datetime", "预测的未来24小时日前电价"]].copy()
future_24_result.to_excel(os.path.join(TABLE_DIR, "13_未来24小时预测结果_演示版.xlsx"), index=False)

fig = plt.figure(figsize=(12, 6))
plt.plot(future_24_result["datetime"], future_24_result["预测的未来24小时日前电价"], marker="o", linewidth=1)
plt.title("未来24小时日前电价预测结果（演示版）")
plt.xlabel("时间")
plt.ylabel("预测电价（USD/MWh）")
plt.xticks(rotation=45)
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "20_未来24小时日前电价预测图_演示版.png"))

# 16. 业务统计摘要
business_summary = []
business_summary.append({"指标": "样本总量", "值": len(df)})
business_summary.append({"指标": "起始时间", "值": str(df["datetime"].min())})
business_summary.append({"指标": "结束时间", "值": str(df["datetime"].max())})
business_summary.append({"指标": "平均日前电价", "值": round(df[TARGET_COL].mean(), 4)})
business_summary.append({"指标": "日前电价最大值", "值": round(df[TARGET_COL].max(), 4)})
business_summary.append({"指标": "日前电价最小值", "值": round(df[TARGET_COL].min(), 4)})
if "actual_load" in df.columns:
    business_summary.append({"指标": "平均实际负荷", "值": round(df["actual_load"].mean(), 4)})
    business_summary.append({"指标": "最大实际负荷", "值": round(df["actual_load"].max(), 4)})
if "forecast_load" in df.columns:
    business_summary.append({"指标": "平均预测负荷", "值": round(df["forecast_load"].mean(), 4)})
if "temperature" in df.columns:
    business_summary.append({"指标": "平均温度", "值": round(df["temperature"].mean(), 4)})
if not metrics_df.empty:
    best_row = metrics_df[metrics_df["模型"] == best_model_name].iloc[0]
    business_summary.append({"指标": "测试集主模型", "值": best_model_name})
    business_summary.append({"指标": "测试集MAE", "值": round(best_row["MAE"], 6)})
    business_summary.append({"指标": "测试集RMSE", "值": round(best_row["RMSE"], 6)})
    business_summary.append({"指标": "测试集MAPE(%)", "值": round(best_row["MAPE(%)"], 6)})
    business_summary.append({"指标": "测试集R2", "值": round(best_row["R2"], 6)})
business_summary.append({"指标": "异常点数量", "值": int((anomaly_df["是否异常"] == 1).sum())})
business_summary.append({"指标": "测试集异常点占比(%)", "值": round(float((anomaly_df["是否异常"] == 1).mean() * 100), 6)})

business_summary_df = pd.DataFrame(business_summary)
business_summary_df.to_excel(os.path.join(TABLE_DIR, "14_业务统计摘要.xlsx"), index=False)

# 17. 结果说明
readme_text = f"""
项目运行完成（彻底去泄漏版）。

一、输入文件
- 主表路径：{MASTER_FILE}

二、输出目录
- 图表目录：{FIG_DIR}
- 结果表目录：{TABLE_DIR}
- 日志目录：{LOG_DIR}

三、本次特别修正
1. 已新增数据泄漏检查报告：03_数据泄漏检查报告.xlsx
2. 已禁用所有当前时点目标派生和后验信息特征：
   - 当前时点 da_price 派生变化率/比值
   - 当前时点 actual_load
   - 当前时点 rt_price 及其分解项
   - 当前时点 load_gap / load_ratio
   - 当前时点观测天气 temperature / wind_speed / precipitation
3. 当前模型仅使用：
   - 历史价格滞后与历史统计
   - 当前 forecast_load（可用前瞻信息）
   - 历史天气滞后与历史负荷滞后
   - 时间日历特征

四、本次输出内容
1. 数据质量检查
2. 数值字段描述统计
3. 数据泄漏检查报告
4. 特征工程后建模表
5. 候选模型验证集结果
6. 测试集模型评估结果
7. 测试集预测结果
8. 特征重要性
9. 异常波动明细
10. 按小时误差统计
11. 滚动回测结果
12. 滚动回测预测明细
13. 未来24小时预测结果（演示版）
14. 业务统计摘要

五、当前阶段建议
- 若本版去泄漏后模型分数下降，这是正常现象；
- 只要仍显著优于两个基线模型，说明模型真实有效；
- 下一步应优先接入真正未来24小时天气预报数据，以进一步提升严格预测场景下的精度。
"""
with open(os.path.join(RESULT_DIR, "README_结果说明_去泄漏版.txt"), "w", encoding="utf-8") as f:
    f.write(readme_text)

log_print("=" * 100)
log_print("全部运行完成！")
log_print(f"图表输出目录：{FIG_DIR}")
log_print(f"结果表输出目录：{TABLE_DIR}")
log_print(f"日志输出目录：{LOG_DIR}")
