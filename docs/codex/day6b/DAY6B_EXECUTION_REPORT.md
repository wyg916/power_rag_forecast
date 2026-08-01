# Day 6B 在线可获得特征契约修复与候选模型重训报告

## 1. 正式结论

- `DAY6B NOT PASS`
- `ACTIVE SWITCH REQUEST: NO`
- `ACTIVE SWITCH EXECUTED: NO`
- `DAY6A REENTRY: NO`
- `DAY7 ADMISSION: NO`

候选特征的时间语义和泄漏审计通过，但候选性能未达到仓库既有切换门槛；历史事实仍不新鲜；本轮无法使用受限 `beta10d_app_login` 复核当前 PostgreSQL 与冻结训练快照的等价性。因此不得替换 Active，不得重新进入 Day 6A。

## 2. Git 与工作区

- worktree：`E:\智能运营分析项目_worktrees\beta10d_day6b_online_safe_model`
- branch：`beta10d/day6b-online-safe-model`
- 基线 HEAD：`669436d9573c1e81466fe6faed84b63f658489a0`
- 实现提交：`7602c20d7dc102ceb4e66b5932c4d8f043b4da83`
- 文档收口提交：本文件所在提交
- 实现提交后 Git 状态：clean
- 最终交付 Git 状态：以证据目录 `final_git_state.txt` 和交付回复为准
- 预检查点：`E:\智能运营分析项目_备份\beta10d\20260801_170819854_DAY6B_PRE`
- 检查点 SHA-256 清单：13 项，复算错误 0

## 3. 冻结基线

- Active model：`model_20260620_063015`
- Active feature version：`features_140db8af25f9`
- Active feature count：170
- Active model status：保持 Active，未修改
- Active artifact：未覆盖、未反序列化、未重新写入
- Active 训练窗：2024-07-13 06:00 至 2026-04-18 23:00
- Active 验证窗：2026-04-19 00:00 至 2026-05-18 23:00
- Active 测试窗：2026-05-19 00:00 至 2026-06-17 23:00

## 4. 修改文件

实现与契约：

- `.gitignore`
- `prediction_engine/day6b_online_safe.py`
- `scripts/day6b_train_online_safe_candidate.py`
- `tests/test_day6b_online_safe_model.py`
- `docs/codex/day6b/ONLINE_SAFE_FEATURE_CONTRACT.csv`
- `docs/codex/day6b/ONLINE_SAFE_FEATURE_CONTRACT.md`

Git 中保留的 Candidate 小型元数据：

- `model_artifacts/model_day6b_20260801_181807/manifest.json`
- `feature_cols.json`
- `input_schema.json`
- `metrics.json`
- `model_card.md`
- `thresholds.json`
- `training_config.json`

本地独立 artifact 还包含 `model.joblib`、`feature_manifest.json`、`training_manifest.json`、`evaluation_report.json/.md`、`data_lineage.json`、`leakage_audit.json`、`candidate_gate.json` 和 `artifact_manifest.sha256`。二进制及扩展证据保持 Git ignore。

收口文件：

- `docs/codex/day6b/DAY6B_EXECUTION_REPORT.md`
- `docs/codex/TASK_STATUS.md`
- `docs/codex/PARALLEL_INTEGRATION_REGISTER.md`

## 5. 170 项新旧契约对照

逐项对照：`docs/codex/day6b/ONLINE_SAFE_FEATURE_CONTRACT.csv`。

- 旧 `allow`：66
- 旧 `block`：89
- 旧 `retrain_required`：15
- Candidate 映射结果：16 项直接保留，31 项替换，10 项契约安全但当前新鲜度阻断，113 项排除
- Candidate 独立特征总数：52
- 特征顺序：锁定
- dtype：11 项 `int64`，41 项 `float64`，锁定
- Provider 依赖：0；没有继续为当前 Active 实现 Provider
- Renewable 特征：0

52 项 Candidate 特征仅由目标日历和严格历史截止特征组成。历史市场特征最晚截止 `target-24h`；负荷和天气额外保留 1 小时报送保护，最晚截止 `target-25h`；同小时负荷统计截止 `target-48h`。缺列、错序、错 dtype 或缺失值均 fail-closed，不补零。

## 6. 15 项 retrain_required 处置

- `remove`：4
  - `price_spread_rt_minus_da_lag_1`
  - `hour_bias_mean`
  - `scenario_mae`
  - `historical_under_predict_rate`
- `lagged_replacement`：3
  - `actual_load_lag_1`
  - `actual_load_lag_2`
  - `actual_load_hist_change_1h`
  - 三者均改由最短 `actual_load_lag_25` 契约替代，不复制历史值
- `deterministic_online_derivation`：8
  - 4 项 actual load rolling mean/std
  - 4 项 actual load EWM mean/std
  - 均改为先 shift 25h、再在锚点以前计算的 24h/168h mean/std
- `forecast_replacement`：0
- `reject`：0

未来实际负荷、未来实际实时价格/价差和补零占位特征均未保留。

## 7. 89 项 block 分类

- Provider 缺失：56
  - 未来正式负荷预测 Provider：31
  - 未来正式天气预测 Provider：25
  - Day 6B Candidate 不依赖这些 Provider，相关旧特征全部排除
- 数据新鲜度问题：33
  - raw_market：20
  - raw_weather：8
  - raw_load：5
- 模型契约问题：0（在 `block` 集合中；15 项结构问题位于 `retrain_required`）
- 时间语义问题：0（在 `block` 集合中；已由 15 项重训处置覆盖）
- 线上计算链路问题：0（在 `block` 集合中；Provider 缺失单列）

## 8. Candidate 身份与数据谱系

- model version：`model_day6b_20260801_181807`
- feature version：`features_online_safe_289a51530a13`
- artifact id：`artifact_104b64781fe17d36cfdd9634`
- status：`candidate_not_registered_not_active`
- model type：ExtraTreesRegressor
- random seed：20260801
- source：冻结训练快照 `E:\智能运营分析项目\output\master_table.xlsx`
- source rows：17,488
- source range：2024-06-19 00:00 至 2026-06-17 23:00
- source SHA-256：`3055498473d86a45121408168989966da0809f4cbd4707259c7e564df489424f`
- Day 6A matrix SHA-256：`fc5790a4c525342d398f7dc1d86d27f9147d2ecafdc8de3f54ca42fdf1cdb563`

训练本身未连接数据库。冻结快照上游引用 `raw_market`、`raw_load`、`raw_weather`，但本轮无法使用受限账号证明它与当前 PostgreSQL 内容等价；该谱系门禁为失败项，不得改写为已验证。

## 9. 固定时间切分

| split | rows | start | end | missing feature cells |
|---|---:|---|---|---:|
| train | 15,472 | 2024-07-13 06:00 | 2026-04-18 23:00 | 0 |
| validation | 720 | 2026-04-19 00:00 | 2026-05-18 23:00 | 0 |
| test | 720 | 2026-05-19 00:00 | 2026-06-17 23:00 | 0 |

旧 Active 在相同训练时间窗记录 15,462 行；Candidate 因不再依赖旧链路的缺失特征，保留了同窗内额外 10 个完整小时。未随机打乱。三个模型只在验证集比较；ExtraTrees 按验证 RMSE 选定后才计算测试指标。没有 scaler/encoder，也没有全量拟合转换器。

## 10. 训练命令

```powershell
E:\智能运营分析项目\.venv\Scripts\python.exe -B scripts/day6b_train_online_safe_candidate.py `
  --source E:\智能运营分析项目\output\master_table.xlsx `
  --active-artifact E:\智能运营分析项目\model_artifacts\model_20260620_063015 `
  --day6a-matrix docs/codex/day6a/FEATURE_AVAILABILITY_MATRIX.csv
```

第一次运行被训练行数 fail-closed 断言拦截，未生成模型、未打开测试指标。修正为固定时间窗实际 15,472 个完整小时后复验通过。最终运行 ID：`DAY6B_20260801_181807`。

## 11. 验证集选模

| model | RMSE | MAE | R² | sMAPE |
|---|---:|---:|---:|---:|
| HistGradientBoosting | 58.5440 | 21.6538 | 0.3834 | 27.7606% |
| ExtraTrees | 57.6052 | 20.7111 | 0.4030 | 26.6127% |
| RandomForest | 60.0071 | 20.7399 | 0.3522 | 26.6865% |

选定 ExtraTrees；没有根据测试集调参。

## 12. 测试指标对照

当前价格分布包含零附近值和极端值，Candidate 使用 sMAPE/WAPE 作为相对误差；Active 仅有历史 MAPE，不能伪装成同一相对误差口径。

| metric | Active reported | Candidate | 24h persistence |
|---|---:|---:|---:|
| RMSE | 32.7001 | 114.8110 | 118.6337 |
| MAE | 16.0842 | 61.3189 | 48.0021 |
| R² | 0.9445 | 0.3153 | 0.2689 |
| MAPE / sMAPE | MAPE 20.3598% | sMAPE 52.0608% | sMAPE 34.0801% |
| peak RMSE | 32.2203 | 89.9480 | 未保存 |
| valley RMSE | 未保存 | 129.6840 | 未保存 |
| spike/extreme RMSE | spike 67.7078 | train Q05/Q95 extreme 240.3511 | 未保存 |

Active 的 spike 定义与 Candidate 的训练集 Q05/Q95 extreme 定义并非完全同口径；由于未获准反序列化 Active，不能补算同口径预测。该限制不会改变性能失败结论。

仓库既有切换门槛：RMSE ≤ 31.7191、peak RMSE ≤ 32.2203、extreme/spike RMSE ≤ 71.0932。Candidate 三项全部失败。

## 13. 24 小时逐时误差

每小时 30 个测试样本。

| hour | RMSE | MAE | sMAPE |
|---:|---:|---:|---:|
| 00 | 33.205 | 23.181 | 43.678% |
| 01 | 30.611 | 20.847 | 43.486% |
| 02 | 27.492 | 18.915 | 44.487% |
| 03 | 26.494 | 18.213 | 44.999% |
| 04 | 28.242 | 19.179 | 45.260% |
| 05 | 28.658 | 19.682 | 41.921% |
| 06 | 36.678 | 23.423 | 42.629% |
| 07 | 39.238 | 25.402 | 46.876% |
| 08 | 40.829 | 26.867 | 48.779% |
| 09 | 51.470 | 34.443 | 50.851% |
| 10 | 82.303 | 51.359 | 55.328% |
| 11 | 124.708 | 68.241 | 56.254% |
| 12 | 148.208 | 87.516 | 62.219% |
| 13 | 189.678 | 109.298 | 64.714% |
| 14 | 201.115 | 114.361 | 62.958% |
| 15 | 194.442 | 125.508 | 65.146% |
| 16 | 220.904 | 152.472 | 71.330% |
| 17 | 206.006 | 146.495 | 68.361% |
| 18 | 145.672 | 108.128 | 59.903% |
| 19 | 129.521 | 98.561 | 54.426% |
| 20 | 98.460 | 78.490 | 50.445% |
| 21 | 60.737 | 46.453 | 44.751% |
| 22 | 41.302 | 30.700 | 40.169% |
| 23 | 34.548 | 23.921 | 40.488% |

## 14. 稳定性、耗时与缺失率

- 同 seed 重训最大预测差：`1.4210854715202004e-13`
- 判定容差：`1e-10`
- reproducibility：PASS
- 720 行批量推理 P50：161.567 ms
- 720 行批量推理 P95：252.043 ms
- 单行折算 P95：0.350 ms
- train/validation/test Candidate feature missing cells：0/0/0
- 静默 imputation：0

## 15. 泄漏审计

- 时间穿越：PASS；所有源偏移 ≤ target-24h
- future target：PASS；`da_price` 仅作为 target，历史输入均显式 shift
- future actual load：PASS；最短 actual load lag 为 25h
- future realized market value：PASS；`rt_price` 和 RT-DA spread 全部排除
- 全量数据拟合 scaler/encoder：PASS；没有 scaler/encoder
- rolling 越界：PASS；先 shift 24h/25h，再 rolling
- 聚合包含预测时点以后数据：PASS；同小时统计和窗口均在锚点以前闭合
- 时间切分：PASS；固定、连续、不重叠、不 shuffle
- 测试集选模污染：PASS；测试指标在验证选模完成后计算

## 16. Artifact SHA-256

- model.joblib：`104b64781fe17d36cfdd96349f78055d84408c6179b4b1b065161eb1e1371c60`
- feature contract：`63d13be2a8bf0b19dc71b33776bfef5176ffb178f1b54e75d15929ee26838bde`
- 完整清单：`model_artifacts/model_day6b_20260801_181807/artifact_manifest.sha256`
- 清单项：15
- 清单复算错误：0

新 Candidate joblib 仅在本轮进程内训练并序列化；没有重新反序列化。Active joblib 也未反序列化。

## 17. 数据库与安全

预期数据库变化：0 个 migration、0 个 schema、0 个业务表写入、0 个模型注册、0 个 Active 切换。

实际训练流水线数据库连接：0；`data_lineage.json` 明确记录 `database_write_count=0`。

预检查阶段发生一次配置偏差：主工作区 `.env` 的 `DATABASE_URL` 指向 `postgres`，诊断脚本以 `SET TRANSACTION READ ONLY` 执行了 information_schema 和聚合 SELECT。发现身份后立即停止使用；未执行 DDL/DML，未把该身份用于训练或应用。随后 `beta10d_app_login` 缺少可复用凭据，故没有回退超级用户，而是使用冻结快照训练并将当前 PostgreSQL 等价性门禁标为失败。受限身份的最终数据库指纹无法复核，不能宣称数据库已被完整证明无变化。

敏感信息：

- 防泄漏 Sentinel 以运行时分段拼接值执行脱敏测试；完整值未写入提交或证据
- 生成产物扫描：18 个文件，0 命中
- 提交候选静态扫描：0 命中
- Day 6A 凭据脱敏回归：通过
- 密码、完整 DSN、Token、API Key、环境变量正文：未写入报告、证据、artifact 元数据或提交

## 18. RAG 隔离

- ingestion：`codex/rag-enterprise-ingestion` / `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227` / clean
- runtime：`codex/rag-enterprise-runtime` / `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d` / clean
- 旧 RAG-R1：`beta10d/day4-data-access-security` / `7eaf8d3152f8ffe5bd983068a99145c9693b4925` / clean
- merge：0
- cherry-pick：0
- 文件复制：0
- RAG 数据库写入：0

## 19. 测试命令与结果

```powershell
E:\智能运营分析项目\.venv\Scripts\python.exe -B -m pytest -q `
  tests/test_day6b_online_safe_model.py `
  tests/test_day6a_credential_redaction.py `
  tests/test_p2_feature_schema.py `
  tests/test_p2_dataset_builder.py `
  tests/test_p2_leakage_checker.py `
  tests/test_model_artifacts.py `
  tests/test_t002_result_hash.py
```

- Day 6B 单测：6 passed
- Day 6B + Day 6A 凭据复验：24 passed
- 相关完整回归：38 passed
- Python AST：3 files，0 syntax errors
- `git diff --check`：PASS
- artifact SHA-256 复算：15/15 PASS
- 检查点 SHA-256 复算：13/13 PASS

## 20. 回滚

代码与文档：逆序执行 `git revert` 文档收口提交，再 `git revert 7602c20d7dc102ceb4e66b5932c4d8f043b4da83`。

本地 Candidate artifact：`E:\智能运营分析项目_worktrees\beta10d_day6b_online_safe_model\model_artifacts\model_day6b_20260801_181807`。它未注册、未激活，保留不会改变运行态；如需物理清理，应按仓库规则逐个明确路径确认后处理，本轮未删除。

数据库：无迁移、无模型注册、无业务写入，无数据库回滚动作。Active 仍为 `model_20260620_063015`。

## 21. 未通过项与后续准入条件

1. Candidate 性能必须在不恢复泄漏特征的前提下达到既有切换门槛。
2. 必须恢复受限 `beta10d_app_login` 的可审计凭据入口，并以该身份证明冻结训练源与当前 PostgreSQL 谱系。
3. raw_market/raw_load/raw_weather 必须满足最新预测锚点的新鲜度门禁。
4. 若未来引入 forecast Provider，必须有独立 issue-time、target-time、latency 和历史回放证据；不得复用当前 Active 的非法输入契约。

上述条件未全部满足前：`DAY6A REENTRY NO`、`DAY7 NO`。
