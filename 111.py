# -*- coding: utf-8 -*-
"""
项目名称：基于公开电力市场数据的电价预测与智能分析系统
当前阶段：EDA分析 + 特征工程 + 首版预测建模
说明：
1）读取 master_table.xlsx 作为唯一建模入口
2）输出EDA图表、建模结果、评估指标、预测结果
3）结果全部保存到指定目录

作者：ChatGPT 按你的需求生成
"""

import os
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

# =========================
# 路径配置
# =========================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "output")
RESULT_DIR = os.path.join(PROJECT_ROOT, "结果")

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
# 工具函数
# =========================
def log_print(msg: str):
    print(msg)
    with open(os.path.join(LOG_DIR, "运行日志.txt"), "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def save_fig(fig, filepath):
    fig.tight_layout()
    fig.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close(fig)


def evaluate_regression(y_true, y_pred, model_name):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mape = np.mean(np.abs((y_true - y_pred) / np.where(y_true == 0, 1e-6, y_true))) * 100
    r2 = r2_score(y_true, y_pred)
    return {
        "模型": model_name,
        "MAE": mae,
        "RMSE": rmse,
        "MAPE(%)": mape,
        "R2": r2
    }


def create_time_features(df, dt_col="datetime"):
    df = df.copy()
    df["hour"] = df[dt_col].dt.hour
    df["day_of_week"] = df[dt_col].dt.dayofweek
    df["month"] = df[dt_col].dt.month
    df["day"] = df[dt_col].dt.day
    df["year"] = df[dt_col].dt.year
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # 周期特征
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    return df


def create_lag_features(df, target_col="da_price"):
    df = df.copy()

    lag_features = {
        target_col: [1, 2, 3, 24, 48, 72, 168],
        "forecast_load": [1, 24, 48, 168],
        "actual_load": [1, 24, 48, 168],
        "temperature": [1, 24, 48, 168],
        "wind_speed": [1, 24],
        "precipitation": [1, 24]
    }

    for col, lags in lag_features.items():
        if col in df.columns:
            for lag in lags:
                df[f"{col}_lag_{lag}"] = df[col].shift(lag)

    return df


def create_rolling_features(df):
    df = df.copy()

    rolling_config = {
        "da_price": [24, 48, 168],
        "forecast_load": [24, 48, 168],
        "actual_load": [24, 48, 168],
        "temperature": [24, 48, 168]
    }

    for col, windows in rolling_config.items():
        if col in df.columns:
            for w in windows:
                df[f"{col}_roll_mean_{w}"] = df[col].shift(1).rolling(window=w).mean()
                df[f"{col}_roll_std_{w}"] = df[col].shift(1).rolling(window=w).std()
                df[f"{col}_roll_min_{w}"] = df[col].shift(1).rolling(window=w).min()
                df[f"{col}_roll_max_{w}"] = df[col].shift(1).rolling(window=w).max()

    return df


def add_business_features(df):
    df = df.copy()

    if "temperature" in df.columns:
        df["temperature_sq"] = df["temperature"] ** 2
        df["cooling_degree"] = np.maximum(df["temperature"] - 22, 0)
        df["heating_degree"] = np.maximum(18 - df["temperature"], 0)

    if "forecast_load" in df.columns and "actual_load" in df.columns:
        df["load_gap"] = df["forecast_load"] - df["actual_load"]

    if "rt_price" in df.columns and "da_price" in df.columns:
        df["price_spread_rt_minus_da"] = df["rt_price"] - df["da_price"]

    # 峰时段标识（可按电力业务习惯微调）
    df["is_peak_hour"] = df["hour"].isin([7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)

    return df


def try_train_model(X_train, y_train):
    """
    优先使用 XGBoost -> LightGBM -> RandomForest
    """
    # 1) 尝试 XGBoost
    try:
        from xgboost import XGBRegressor
        model = XGBRegressor(
            n_estimators=400,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train, y_train)
        return model, "XGBoost"
    except Exception as e:
        log_print(f"XGBoost 不可用，原因：{e}")

    # 2) 尝试 LightGBM
    try:
        from lightgbm import LGBMRegressor
        model = LGBMRegressor(
            n_estimators=400,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42
        )
        model.fit(X_train, y_train)
        return model, "LightGBM"
    except Exception as e:
        log_print(f"LightGBM 不可用，原因：{e}")

    # 3) 回退 RandomForest
    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=12,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)
    return model, "RandomForest"


def get_feature_importance(model, feature_names):
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


# =========================
# 1. 读取数据
# =========================
log_print("=" * 80)
log_print("开始读取主表数据...")

if not os.path.exists(MASTER_FILE):
    raise FileNotFoundError(f"未找到主表文件：{MASTER_FILE}")

df = pd.read_excel(MASTER_FILE)

log_print(f"主表读取成功，数据形状：{df.shape}")
log_print(f"字段列表：{list(df.columns)}")

# 时间列处理
if "datetime" not in df.columns:
    raise ValueError("主表中未找到 datetime 字段，请检查文件结构。")

df["datetime"] = pd.to_datetime(df["datetime"])
df = df.sort_values("datetime").reset_index(drop=True)

# 去重
before_drop = len(df)
df = df.drop_duplicates(subset=["datetime"]).reset_index(drop=True)
after_drop = len(df)
log_print(f"按 datetime 去重后：{before_drop} -> {after_drop}")

# =========================
# 2. 数据质量检查
# =========================
log_print("=" * 80)
log_print("开始数据质量检查...")

quality_rows = []
for col in df.columns:
    quality_rows.append({
        "字段名": col,
        "数据类型": str(df[col].dtype),
        "缺失值数量": int(df[col].isna().sum()),
        "缺失率(%)": round(df[col].isna().mean() * 100, 4),
        "唯一值数量": int(df[col].nunique(dropna=True))
    })

quality_df = pd.DataFrame(quality_rows)
quality_df.to_excel(os.path.join(TABLE_DIR, "01_数据质量检查.xlsx"), index=False)

log_print("数据质量检查完成，已输出：01_数据质量检查.xlsx")

# 数值统计
numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
desc_df = df[numeric_cols].describe().T
desc_df.to_excel(os.path.join(TABLE_DIR, "02_数值字段描述统计.xlsx"))

# =========================
# 3. EDA 图表输出
# =========================
log_print("=" * 80)
log_print("开始输出EDA图表...")

# 3.1 电价时间序列图
fig = plt.figure(figsize=(16, 6))
plt.plot(df["datetime"], df["da_price"], linewidth=0.8)
plt.title("DOM区域日前电价时间序列图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "01_日前电价时间序列图.png"))

# 3.2 实际负荷时间序列图
if "actual_load" in df.columns:
    fig = plt.figure(figsize=(16, 6))
    plt.plot(df["datetime"], df["actual_load"], linewidth=0.8)
    plt.title("DOM区域实际负荷时间序列图")
    plt.xlabel("时间")
    plt.ylabel("实际负荷（MW）")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "02_实际负荷时间序列图.png"))

# 3.3 按小时平均电价
hourly_mean = df.groupby("hour", as_index=False)["da_price"].mean()
fig = plt.figure(figsize=(10, 5))
plt.plot(hourly_mean["hour"], hourly_mean["da_price"], marker="o", linewidth=1)
plt.title("按小时平均日前电价")
plt.xlabel("小时")
plt.ylabel("平均日前电价（USD/MWh）")
plt.xticks(range(24))
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "03_按小时平均日前电价.png"))

# 3.4 按星期平均电价
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

# 3.5 月均电价
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

# 3.6 峰谷价差（按天）
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

# 3.7 电价与负荷关系散点图
if "actual_load" in df.columns:
    sample_df = df[["actual_load", "da_price"]].dropna()
    if len(sample_df) > 5000:
        sample_df = sample_df.sample(5000, random_state=42)

    fig = plt.figure(figsize=(8, 6))
    plt.scatter(sample_df["actual_load"], sample_df["da_price"], s=8, alpha=0.5)
    plt.title("实际负荷与日前电价关系散点图")
    plt.xlabel("实际负荷（MW）")
    plt.ylabel("日前电价（USD/MWh）")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "07_实际负荷与日前电价关系散点图.png"))

# 3.8 温度与电价关系散点图
if "temperature" in df.columns:
    sample_df = df[["temperature", "da_price"]].dropna()
    if len(sample_df) > 5000:
        sample_df = sample_df.sample(5000, random_state=42)

    fig = plt.figure(figsize=(8, 6))
    plt.scatter(sample_df["temperature"], sample_df["da_price"], s=8, alpha=0.5)
    plt.title("温度与日前电价关系散点图")
    plt.xlabel("温度（℃）")
    plt.ylabel("日前电价（USD/MWh）")
    plt.grid(alpha=0.3)
    save_fig(fig, os.path.join(FIG_DIR, "08_温度与日前电价关系散点图.png"))

# 3.9 小时-星期热力表
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

log_print("EDA图表输出完成。")

# =========================
# 4. 特征工程
# =========================
log_print("=" * 80)
log_print("开始特征工程...")

# 若主表里已有这些字段，也重新覆盖确保一致
df = create_time_features(df, dt_col="datetime")
df = add_business_features(df)
df = create_lag_features(df, target_col="da_price")
df = create_rolling_features(df)

# 构造仅使用“预测时点可得信息”的首版特征
candidate_features = [
    # 日历特征
    "hour", "day_of_week", "month", "year", "is_weekend",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos",

    # 天气与负荷（当前数据先使用，后续若你有天气预报数据可替换成预测天气）
    "forecast_load", "temperature", "wind_speed", "precipitation",
    "temperature_sq", "cooling_degree", "heating_degree", "is_peak_hour",

    # 历史价格滞后
    "da_price_lag_1", "da_price_lag_2", "da_price_lag_3",
    "da_price_lag_24", "da_price_lag_48", "da_price_lag_72", "da_price_lag_168",

    # 负荷滞后
    "forecast_load_lag_1", "forecast_load_lag_24", "forecast_load_lag_48", "forecast_load_lag_168",
    "actual_load_lag_1", "actual_load_lag_24", "actual_load_lag_48", "actual_load_lag_168",

    # 天气滞后
    "temperature_lag_1", "temperature_lag_24", "temperature_lag_48", "temperature_lag_168",
    "wind_speed_lag_1", "wind_speed_lag_24",
    "precipitation_lag_1", "precipitation_lag_24",

    # 滚动统计
    "da_price_roll_mean_24", "da_price_roll_std_24", "da_price_roll_min_24", "da_price_roll_max_24",
    "da_price_roll_mean_48", "da_price_roll_std_48",
    "da_price_roll_mean_168", "da_price_roll_std_168",

    "forecast_load_roll_mean_24", "forecast_load_roll_std_24",
    "forecast_load_roll_mean_48", "forecast_load_roll_std_48",
    "forecast_load_roll_mean_168", "forecast_load_roll_std_168",

    "actual_load_roll_mean_24", "actual_load_roll_std_24",
    "temperature_roll_mean_24", "temperature_roll_std_24"
]

candidate_features = [f for f in candidate_features if f in df.columns]

target_col = "da_price"

model_df = df[["datetime", target_col] + candidate_features].copy()
model_df = model_df.dropna().reset_index(drop=True)

log_print(f"特征工程完成，建模数据形状：{model_df.shape}")
log_print(f"特征数量：{len(candidate_features)}")

model_df.to_excel(os.path.join(TABLE_DIR, "03_建模数据样本.xlsx"), index=False)

# =========================
# 5. 时间切分训练/测试集
# =========================
log_print("=" * 80)
log_print("开始时间序列切分...")

# 最近30天作为测试集
max_dt = model_df["datetime"].max()
test_start_dt = max_dt - pd.Timedelta(days=30)

train_df = model_df[model_df["datetime"] < test_start_dt].copy()
test_df = model_df[model_df["datetime"] >= test_start_dt].copy()

X_train = train_df[candidate_features]
y_train = train_df[target_col]

X_test = test_df[candidate_features]
y_test = test_df[target_col]

log_print(f"训练集：{train_df.shape}")
log_print(f"测试集：{test_df.shape}")
log_print(f"测试开始时间：{test_start_dt}")

# =========================
# 6. 基线模型
# =========================
log_print("=" * 80)
log_print("开始训练基线模型...")

metrics_list = []

# 基线1：前24小时同小时值
baseline_pred_24 = test_df["da_price_lag_24"].values
metrics_list.append(evaluate_regression(y_test, baseline_pred_24, "基线模型_前24小时同小时"))

# 基线2：前168小时同小时值（上周同一时刻）
if "da_price_lag_168" in test_df.columns:
    baseline_pred_168 = test_df["da_price_lag_168"].values
    metrics_list.append(evaluate_regression(y_test, baseline_pred_168, "基线模型_上周同时刻"))

# 线性回归
lr_model = LinearRegression()
lr_model.fit(X_train, y_train)
lr_pred = lr_model.predict(X_test)
metrics_list.append(evaluate_regression(y_test, lr_pred, "线性回归"))

# =========================
# 7. 树模型训练
# =========================
log_print("=" * 80)
log_print("开始训练主模型...")

main_model, model_name = try_train_model(X_train, y_train)
main_pred = main_model.predict(X_test)
metrics_list.append(evaluate_regression(y_test, main_pred, model_name))

metrics_df = pd.DataFrame(metrics_list).sort_values("RMSE").reset_index(drop=True)
metrics_df.to_excel(os.path.join(TABLE_DIR, "04_模型评估结果.xlsx"), index=False)

log_print("模型评估结果：")
log_print(str(metrics_df))

# =========================
# 8. 预测结果保存
# =========================
pred_result = test_df[["datetime", "da_price"]].copy()
pred_result.rename(columns={"da_price": "真实值"}, inplace=True)
pred_result["基线_前24小时同小时"] = baseline_pred_24

if "da_price_lag_168" in test_df.columns:
    pred_result["基线_上周同一时刻"] = baseline_pred_168

pred_result["线性回归预测值"] = lr_pred
pred_result[f"{model_name}预测值"] = main_pred
pred_result["预测误差"] = pred_result[f"{model_name}预测值"] - pred_result["真实值"]
pred_result["绝对误差"] = np.abs(pred_result["预测误差"])

pred_result.to_excel(os.path.join(TABLE_DIR, "05_测试集预测结果.xlsx"), index=False)

# =========================
# 9. 预测结果图
# =========================
log_print("=" * 80)
log_print("开始输出预测结果图...")

# 9.1 测试集整体真实值 vs 预测值
fig = plt.figure(figsize=(16, 6))
plt.plot(pred_result["datetime"], pred_result["真实值"], label="真实值", linewidth=1)
plt.plot(pred_result["datetime"], pred_result[f"{model_name}预测值"], label=f"{model_name}预测值", linewidth=1)
plt.title(f"测试集真实值与{model_name}预测值对比图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.legend()
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "10_测试集真实值与主模型预测值对比图.png"))

# 9.2 最后7天局部预测图
last_7d = pred_result[pred_result["datetime"] >= pred_result["datetime"].max() - pd.Timedelta(days=7)].copy()
fig = plt.figure(figsize=(16, 6))
plt.plot(last_7d["datetime"], last_7d["真实值"], label="真实值", linewidth=1.2)
plt.plot(last_7d["datetime"], last_7d[f"{model_name}预测值"], label=f"{model_name}预测值", linewidth=1.2)
plt.title("最后7天真实值与主模型预测值局部对比图")
plt.xlabel("时间")
plt.ylabel("日前电价（USD/MWh）")
plt.legend()
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "11_最后7天局部预测对比图.png"))

# 9.3 误差时间序列图
fig = plt.figure(figsize=(16, 6))
plt.plot(pred_result["datetime"], pred_result["预测误差"], linewidth=0.8)
plt.axhline(0, linestyle="--", linewidth=1)
plt.title(f"{model_name}预测误差时间序列图")
plt.xlabel("时间")
plt.ylabel("预测误差")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "12_主模型预测误差时间序列图.png"))

# 9.4 绝对误差分布图
fig = plt.figure(figsize=(10, 6))
plt.hist(pred_result["绝对误差"], bins=50)
plt.title(f"{model_name}绝对误差分布图")
plt.xlabel("绝对误差")
plt.ylabel("频数")
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "13_主模型绝对误差分布图.png"))

# =========================
# 10. 特征重要性
# =========================
log_print("=" * 80)
log_print("开始输出特征重要性...")

feature_importance_df = get_feature_importance(main_model, candidate_features)
feature_importance_df.to_excel(os.path.join(TABLE_DIR, "06_特征重要性.xlsx"), index=False)

if not feature_importance_df.empty:
    top_n = min(20, len(feature_importance_df))
    top_df = feature_importance_df.head(top_n).iloc[::-1]

    fig = plt.figure(figsize=(10, 8))
    plt.barh(top_df["特征"], top_df["重要性"])
    plt.title(f"{model_name}前{top_n}个特征重要性")
    plt.xlabel("重要性")
    plt.ylabel("特征")
    plt.grid(alpha=0.3, axis="x")
    save_fig(fig, os.path.join(FIG_DIR, "14_主模型特征重要性图.png"))

# =========================
# 11. 未来24小时预测（首版）
# =========================
log_print("=" * 80)
log_print("开始生成未来24小时预测结果...")

# 首版方案说明：
# 使用主表最后24小时作为“待预测窗口”演示
# 若后续接入真实未来天气预报和负荷预测，可替换对应字段后正式外推

future_24 = model_df.tail(24).copy()
future_24 = future_24[["datetime"] + candidate_features].copy()
future_24["预测的未来24小时日前电价"] = main_model.predict(future_24[candidate_features])

future_24_result = future_24[["datetime", "预测的未来24小时日前电价"]].copy()
future_24_result.to_excel(os.path.join(TABLE_DIR, "07_未来24小时预测结果_演示版.xlsx"), index=False)

fig = plt.figure(figsize=(12, 6))
plt.plot(future_24_result["datetime"], future_24_result["预测的未来24小时日前电价"], marker="o", linewidth=1)
plt.title("未来24小时日前电价预测结果（演示版）")
plt.xlabel("时间")
plt.ylabel("预测电价（USD/MWh）")
plt.xticks(rotation=45)
plt.grid(alpha=0.3)
save_fig(fig, os.path.join(FIG_DIR, "15_未来24小时日前电价预测图_演示版.png"))

# =========================
# 12. 业务统计结果输出
# =========================
log_print("=" * 80)
log_print("开始输出业务统计结果...")

business_summary = []

business_summary.append({
    "指标": "样本总量",
    "值": len(df)
})
business_summary.append({
    "指标": "起始时间",
    "值": str(df["datetime"].min())
})
business_summary.append({
    "指标": "结束时间",
    "值": str(df["datetime"].max())
})
business_summary.append({
    "指标": "平均日前电价",
    "值": round(df["da_price"].mean(), 4)
})
business_summary.append({
    "指标": "日前电价最大值",
    "值": round(df["da_price"].max(), 4)
})
business_summary.append({
    "指标": "日前电价最小值",
    "值": round(df["da_price"].min(), 4)
})

if "actual_load" in df.columns:
    business_summary.append({
        "指标": "平均实际负荷",
        "值": round(df["actual_load"].mean(), 4)
    })
    business_summary.append({
        "指标": "最大实际负荷",
        "值": round(df["actual_load"].max(), 4)
    })

if "forecast_load" in df.columns:
    business_summary.append({
        "指标": "平均预测负荷",
        "值": round(df["forecast_load"].mean(), 4)
    })

if "temperature" in df.columns:
    business_summary.append({
        "指标": "平均温度",
        "值": round(df["temperature"].mean(), 4)
    })

business_summary_df = pd.DataFrame(business_summary)
business_summary_df.to_excel(os.path.join(TABLE_DIR, "08_业务统计摘要.xlsx"), index=False)

# =========================
# 13. 保存最终建模表
# =========================
model_df.to_excel(os.path.join(TABLE_DIR, "09_特征工程后建模表.xlsx"), index=False)

# =========================
# 14. 输出说明文件
# =========================
readme_text = f"""
项目运行完成。

一、输入文件
- 主表路径：{MASTER_FILE}

二、输出目录
- 图表目录：{FIG_DIR}
- 结果表目录：{TABLE_DIR}
- 日志目录：{LOG_DIR}

三、本次输出内容
1. 数据质量检查
2. 数值字段描述统计
3. EDA图表
4. 建模样本表
5. 模型评估结果
6. 测试集预测结果
7. 特征重要性
8. 未来24小时预测结果（演示版）
9. 业务统计摘要

四、主模型
- 使用模型：{model_name}

五、当前阶段说明
- 当前已完成：EDA分析 + 特征工程 + 首版预测建模
- 下一步建议：
  1）接入真正未来24小时天气预报数据
  2）严格构建“可用于真实预测时点”的未来特征
  3）做滚动窗口回测
  4）增加异常识别与AI自动解读模块
"""

with open(os.path.join(RESULT_DIR, "README_结果说明.txt"), "w", encoding="utf-8") as f:
    f.write(readme_text)

log_print("=" * 80)
log_print("全部运行完成！")
log_print(f"图表输出目录：{FIG_DIR}")
log_print(f"结果表输出目录：{TABLE_DIR}")
log_print(f"日志输出目录：{LOG_DIR}")
