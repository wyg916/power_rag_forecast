# Day 6A Active 模型 170 项线上特征可用性审计

## 结论

- 门禁：`ACTIVE MODEL ONLINE FEATURE CONTRACT NOT PASS`
- Active 模型：`model_20260620_063015`
- 特征版本：`features_140db8af25f9`
- 特征总数：`170`；dtype 均为 `numeric`；顺序与 artifact `feature_cols.json` 完全一致。
- 必须重训/换模的阻断特征：`15`。
- 可再生能源特征：`0`；当前 Active 模型不依赖可再生能源输入，Renewable Provider 不需要进入本模型在线输入链。
- 当前历史事实最大时间：`2026-06-18 23:00:00`，审计日为 `2026-08-01`；历史准入当前也不满足新鲜度要求。

## 决策统计

| final_decision | count |
|---|---:|
| `allow` | 66 |
| `block` | 89 |
| `retrain_required` | 15 |

`block` 包含历史新鲜度 33 项、正式负荷预测 31 项和正式天气预测 25 项；`retrain_required` 包含未来实际负荷语义 11 项、未来实时价差 1 项和未实现补零占位特征 3 项。

## 阻断特征

| feature_name | reason |
|---|---|
| `price_spread_rt_minus_da_lag_1` | `high_future_actual_market_or_proxy_substitution` |
| `actual_load_lag_1` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_lag_2` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_hist_change_1h` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_roll_mean_24` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_roll_std_24` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_roll_mean_168` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_roll_std_168` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_ewm_mean_24` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_ewm_std_24` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_ewm_mean_168` | `high_future_actual_or_proxy_semantic_mismatch` |
| `actual_load_ewm_std_168` | `high_future_actual_or_proxy_semantic_mismatch` |
| `hour_bias_mean` | `high_schema_semantics_and_silent_fallback` |
| `scenario_mae` | `high_schema_semantics_and_silent_fallback` |
| `historical_under_predict_rate` | `high_schema_semantics_and_silent_fallback` |

## 关键证据

1. `hour_bias_mean`、`scenario_mae`、`historical_under_predict_rate` 在当前引擎中没有正式误差记忆来源，缺列时直接注入常量 `0.0`；它们仍被 Active schema 要求。
2. `actual_load_lag_1/2`、短期变化、rolling 和 EWM 在 24 小时递归的第 2–24 点会跨入预测窗口；要保持训练语义就需要未来实际负荷。当前代码改用 `forecast_load_bias_adjusted` 代理，违反严格特征语义。
3. `price_spread_rt_minus_da_lag_1` 在第 2–24 点需要尚未发生的实时价差；当前代码改用历史同小时代理，属于禁止的未来事实替代。
4. 现有负荷刷新只调用 PJM `load_frcstd_hist` 历史 feed；现有未来天气失败后回退历史同小时天气；二者都不能作为 Day 6A 正式 Provider PASS 证据。
5. 快速预测入口仍存在缺特征补 `0.0` 路径；正式引擎虽对最终 170 项执行 NaN/Inf fail-closed，但其 base frame 已提前注入上述代理。

## 门禁后续

- 根据 Day 6A 任务书，Active 模型线上特征契约失败后必须停止 Provider、批次、迁移和模型输入快照实施。
- 不允许修改 Active 输入 schema 或继续把代理/占位值包装为真实线上输入。
- 重新准入路径：重训并移除/正式实现三项误差记忆特征；移除需要未来实际负荷/实时价差的递归特征，或用在训练与线上完全一致、预测时可得的正式预测特征重新训练和验证。

## 完整矩阵

逐项审计见 `FEATURE_AVAILABILITY_MATRIX.csv`。矩阵字段包含来源域、可用性、回看窗口、预测窗口、Provider/表、预测时生成性、泄漏风险、fallback、Active 必需性和最终决策。
