# P2-0 预测链路审计与 P2-1 数据集构建底座报告

生成时间：2026-06-13 00:10（本地运行态）

## 1. Git 信息

- 当前分支：`p2-forecast-accuracy-model-engineering`
- P2 基线来源提交：`410d7c4c9fa6adf77413334d14a7e66254570df0`
- 远程仓库：`https://github.com/wyg916/power_rag_forecast.git`
- 本轮是否修改业务逻辑：否。现阶段只新增 `prediction_engine/dataset_builder.py`、聚焦测试和本报告；未修改现有预测算法、预测 API、P1 SQL 安全拦截、AI 查数链路。
- 本轮是否删除 legacy 脚本：否。
- 本轮是否提交模型权重或大体积工件：否。`model_artifacts/` 和 `output/` 仍由 `.gitignore` 忽略。

## 2. 当前预测链路总览

### 训练入口

- 主要 legacy 训练入口仍是 `高峰尖刺增强版_电力市场电价预测与智能分析系统_v4_fix1.py`。
- `prediction_engine/pipeline.py` 通过 `load_engine_module().main()` 包裹 legacy 引擎。
- `prediction_engine/model_trainer.py` 已存在模型训练封装与工件保存能力，会输出 `feature_cols.json`、`training_config.json`、`metrics.json`、`thresholds.json`、`input_schema.json`、`manifest.json`、`model_card.md`。
- 后端/任务中心训练入口：`main_daily_run.py --retrain-model`，任务名 `retrain_model`。
- 存在 legacy 大脚本，当前 P2 未删除或替换。

### 预测入口

- 快速预测入口：`main_daily_run.py --fast-forecast` -> `services/prediction_service.py` -> `prediction_engine/fast_forecast.py`。
- 刷新并预测入口：`main_daily_run.py --refresh-data --fast-forecast`，任务名 `refresh_fast_forecast`。
- 正式/完整预测入口：`01_run_prediction.py` -> `services.prediction_service.run_prediction` -> legacy 引擎。
- 后端 API 入口：`POST /api/forecast/run`，支持 `fast_forecast`、`refresh_fast_forecast`、`retrain_model`。
- 前端触发入口：`frontend/src/api.ts` 的 `runForecast()` 调用 `/api/forecast/run`；`ForecastCenterPage` 提供“更新预测”；`ModelCenterPage` 可触发训练任务。
- 任务中心参与预测：`backend/app/workers/task_commands.py` 和 `backend/app/task_manager.py` 映射预测/训练命令。

## 3. 当前数据表与字段使用情况

### 事实源状态

- `raw_market`：存在，P2 builder 实测 17,518 个小时聚合点，使用 `da_price`、`rt_price`、`lmp`。
- `raw_load`：存在，P2 builder 实测 17,518 个小时聚合点，使用 `actual_load`、`forecast_load`。
- `raw_weather`：存在，P2 builder 实测 17,520 个小时聚合点，使用 `temperature`、`humidity`、`wind_speed`；缺失 `precipitation`，已记录 warning 并跳过。
- `raw_renewable`：表存在，但当前实测聚合后 0 行；不进入有效训练特征。
- `feature_importance`：存在，实测 170 行；P2-1 builder 暂只记录状态，不作为训练特征。
- `forecast_results`：存在，实测 24 行；P2-1 builder 暂只记录状态，不作为训练特征，避免把预测结果反灌训练特征。

### Legacy fallback 状态

- 当前生产预测链路仍会通过 `database_utils.export_prediction_inputs_from_database()` 将 PostgreSQL 数据导出为 Excel，legacy 脚本再读取 Excel。
- P2 新增 `dataset_builder` 默认不依赖 Excel/CSV fallback。
- 只有显式设置 `allow_legacy_fallback=True` 时，才允许读取 `master_table.xlsx`，并写入 warning。

## 4. 当前训练目标与粒度

- 主要预测目标：`da_price`。
- legacy 脚本中 `TARGET_COL = "da_price"`。
- 主要时间字段：`datetime`。
- 当前粒度：小时级。
- 其他价格字段：`rt_price`、`lmp` 当前只允许作为滞后特征来源，不允许当前小时直接进入 `feature_columns`。

## 5. 当前特征与泄露风险

### 已识别特征类型

- 时间特征：hour、day_of_week、month、day、day_of_year、week_of_year、weekend、sin/cos 周期特征。
- 高峰/尖峰特征：morning peak、evening peak、peak hour、legacy spike classifier。
- 滞后特征：`da_price`、`forecast_load`、`actual_load`、`rt_price`、`lmp` 的安全滞后字段。
- rolling/EWM 类特征：legacy 中已有 rolling/EWM；P2 builder 当前新增 shifted rolling mean/std/max。
- 负荷特征：`forecast_load` 当前值、`actual_load` 滞后值。
- 天气特征：`temperature`、`wind_speed` 当前值及滞后/rolling；当前天气类特征在 schema 中标记为必须由预测时可用的天气预报字段提供。
- 可再生能源：当前表为空，P2 builder 自动排除全空派生特征。

### 泄露控制结论

- P2 builder 默认按时间切分，不随机打乱。
- `da_price`、当前 `actual_load`、当前 `rt_price`、当前 `lmp`、`predicted_price`、`corrected_predicted_price`、`forecast_datetime` 不进入训练特征。
- 所有 lag/rolling 特征先 shift 再聚合。
- 当前天气派生特征只有在预测时提供等价天气预报字段时才允许使用。
- `output/p2/leakage_check.json` 实测结果：`ok=true`。

## 6. 当前模型工件和版本机制

- 本地模型工件目录：`model_artifacts/`。
- 最新可见工件目录：`model_20260526_192921`。
- 工件包含：`base_model.joblib`、`peak_model.joblib`、`spike_classifier.joblib`、`p90_model.joblib`、`feature_cols.json`、`input_schema.json`、`metrics.json`、`training_config.json`、`thresholds.json`、`manifest.json`、`model_card.md`。
- active model 机制：`model_ops/active_model_loader.py` 优先从 `model_registry` 读取 active 模型；数据库不可用时 fallback 到 `config/model_learning.json` 中的 `active_artifact_path`。
- 注册机制：`model_ops/model_registry.py` 可注册 candidate/active 模型，但实现偏 MySQL `ON DUPLICATE KEY` 风格，后续 P2 需要核对 PostgreSQL 运行态兼容性。

## 7. 当前评估体系

### 已存在能力

- legacy 脚本中已有 MAE、RMSE、MAPE、R2。
- legacy 脚本中已有高峰/尖峰相关评估与 spike classifier。
- legacy 脚本中已有 feature importance 输出。
- legacy 脚本中已有 rolling backtest 概念。
- `prediction_engine/evaluation.py` 对 legacy 评估函数做了薄封装。

### 缺口

- 评估体系仍主要内嵌在 legacy 大脚本中，不是独立、可复现、可单测的 P2 model ops 模块。
- 缺少统一 baseline 对比协议，不能只看单次训练结果。
- 缺少独立的 `feature_schema.json` 训练/预测一致性校验入口。
- 极端天气指标未形成标准输出。
- 当前 backtest 需要进一步工程化为固定时间切分、多窗口回测、整体/高峰/尖峰/极端天气分组指标。

## 8. P2-1 dataset_builder 落地结果

新增模块：`prediction_engine/dataset_builder.py`

### 默认行为

- 默认从 PostgreSQL 读取 `raw_market`、`raw_load`、`raw_weather`、`raw_renewable`。
- `feature_importance` 和 `forecast_results` 只记录存在性和行数，不默认作为训练特征。
- 不默认依赖 Excel/CSV legacy fallback。
- 支持显式 legacy fallback，但必须传入 `allow_legacy_fallback=True`。
- 支持按时间切分 train/validation/test。
- 支持输出 `feature_schema.json`、`dataset_summary.json`、`leakage_check.json`。

### 本地真实运行结果

- 命令：`python -m prediction_engine.dataset_builder --output-dir output/p2 --output-format csv`
- 输出：
  - `output/p2/dataset_summary.json`
  - `output/p2/feature_schema.json`
  - `output/p2/leakage_check.json`
  - `output/p2/train_dataset.csv`
  - `output/p2/validation_dataset.csv`
  - `output/p2/test_dataset.csv`
- 数据起止：`2024-06-10T00:00:00` 至 `2026-06-09T23:00:00`
- 样本量：17,518
- 特征数：56
- 训练集：16,077 行，`2024-06-10T00:00:00` 至 `2026-04-10T22:00:00`
- 验证集：720 行，`2026-04-10T23:00:00` 至 `2026-05-10T22:00:00`
- 测试集：721 行，`2026-05-10T23:00:00` 至 `2026-06-09T23:00:00`
- schema 一致性：`ok=true`
- 泄露检查：`ok=true`
- warning：`raw_weather missing columns skipped by dataset builder: precipitation`

## 9. 测试结果

- `python -m py_compile prediction_engine\dataset_builder.py tests\test_p2_dataset_builder.py`：通过。
- `python -m pytest tests/test_p2_dataset_builder.py -q --durations=20`：2 passed。

覆盖点：

- PostgreSQL 事实表读取路径。
- 时间顺序切分。
- `feature_schema.json` 生成。
- schema 一致性检查。
- 禁止默认 legacy fallback。
- 排除当前目标、当前实际负荷、当前实时价格、当前 LMP、当前 renewable 字段等泄露字段。
- 天气当前特征标注为预测时必须由天气预报提供。

## 10. 当前问题与风险

- 预测/训练主链路仍依赖 legacy 大脚本，P2 后续需要逐步以新模块包裹 backtest、baseline、训练和注册，不宜一次性替换。
- 现有 PostgreSQL `raw_weather` 缺少 `precipitation`，builder 已降级跳过，但后续字段目录和 schema 应统一。
- `raw_renewable` 当前为空，不能支撑 renewable 相关模型特征。
- 当前 active model 注册机制需要确认 PostgreSQL 兼容性。
- 当前 `output/p2` 为本地运行输出，按 `.gitignore` 不提交；报告记录其生成路径与核心指标。

## 11. 是否建议进入 P2-1 工程落地

建议进入 P2-1 的下一步工程落地。

理由：

- P2 分支已建立。
- P2-0 链路审计已完成。
- P2-1 dataset builder 已新增，且默认以 PostgreSQL 事实源构建训练集。
- 已输出 feature schema、dataset summary、leakage check。
- 已按时间切分 train/validation/test，无随机打乱。
- 已有聚焦测试覆盖关键安全约束。
- 未修改现有预测算法、预测 API、P1 SQL 安全拦截或 AI 查数链路。

下一步建议在同一 P2 分支继续实现：

- baseline evaluator。
- 时间切分 backtest runner。
- 整体/高峰/尖峰/极端天气分组指标。
- 训练与预测 feature schema 一致性校验。
- active model 注册的 PostgreSQL 兼容性核查。
