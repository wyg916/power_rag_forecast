# PROJECT1 v2.12.0 并行任务 A：核心预测 P0 与业务链报告

- 任务：`PROJECT1_V2_12_A_CORE_P0_AND_BUSINESS_CHAIN`
- 角色：`CORE_FUNCTION_OWNER`
- 结论：`PASS`
- 工作树：`E:/智能运营分析项目_worktrees/project1_v2.12.0_core_p0`
- 分支：`codex/project1-v2.12.0-core-p0`
- 起始 SHA：`3b6eb33df96ece08a60acce802d6ec249ec5a826`
- 验收时间：2026-08-22 19:57 +08:00
- 开工检查点：`backups/phase3/20260822_184801_PROJECT1_V2_12_A_CORE_P0_PRE/`

## 1. 根因

P0 由三个串联断点造成：

1. `/api/forecast/run` 的两个预测模式仍路由到 `fast_forecast/today_analysis` 旧命令，而正式 PostgreSQL 预测实现是 `price_predict` 专用 Celery 任务，导致页面入口没有进入正式预测事务。
2. 旧 handler 用当前 linked worktree 的 `project_paths()`、`.codex_envs` 和 `.venv` 查找输入与隔离运行时；该 worktree 不包含共享大资产，因此在模型推理前即报“严格 24×170 预测输入不存在”。
3. 旧 handler 先在事务外推理，再只写 `forecast_runs/forecast_results`，没有把输入批次和 24 个快照与结果放在同一事务，也把历史冻结输入标为 `real`；因此缺少可审计、可幂等消费的输入事实。

## 2. 实现闭环

- 两个公开预测模式统一归一化为 `price_predict`，并把调用方 `idempotency_key` 传入正式 worker。
- 运行资产优先使用显式只读资产根；linked worktree 未配置时，从 PostgreSQL Active 模型事实中的 `artifact_path` 反向解析共享资产根，不硬编码机器路径。
- 正式 worker 在反序列化前核对 PostgreSQL 唯一 Active 模型与静态 artifact manifest；隔离 Python 仍执行既有 `scripts/t003_isolated_inference.py`，父进程只读取 JSON/NumPy 输出。
- 在同一 PostgreSQL 事务内写入 `forecast_input_batches`、24 个 `forecast_input_snapshots`、`forecast_runs` 和 24 个 `forecast_results`；任何异常整笔回滚。
- 业务幂等键绑定请求键、输入 hash、model/artifact/feature/schema 身份，并用 PostgreSQL 事务级 advisory lock 串行化并发重复请求。
- 历史输入保持 `source_type=historical`、`is_simulated=false`、`freshness_status=stale`，禁止冒充当前实时事实。
- 报告 metadata/content 与策略 evidence 继续携带同一 `input_batch_id`、model/feature/schema/artifact 身份；历史策略允许人工审计，但发布保持 fail-closed。

## 3. PostgreSQL 唯一模型事实

| 字段 | 值 |
|---|---|
| model_id | `price_da_price_model_20260620_063015` |
| model_version | `model_20260620_063015` |
| artifact_id | `artifact_f6689b533cb8fc94e18ac53a` |
| artifact_hash | `f6689b533cb8fc94e18ac53a399e9bac5a4f6fb4c4df354c701182fe23c70f59` |
| feature_version | `features_140db8af25f9` |
| schema_hash | `a855692756793862b1fcfd3c68c701d1ad231b32e6581797d74f4a8ab4199281` |
| model_role | `blended` |
| source | `validated_local_artifact` |
| created_at | `2026-07-18 21:07:26.939628` |
| status | `active` |

本轮没有创建第二套模型注册事实，也没有改写 Active；运行前后都由 PostgreSQL 唯一 Active 行决定消费身份，文件仅作为该数据库事实指向且 hash 已核对的 artifact。

`model_versions` 当前 5 行均为负荷预测展示/历史 seed 记录，缺少本任务价格模型所需的 domain、target、artifact/feature/schema hash 身份，不能作为 `price/da_price` 正式预测事实源；正式 worker 只消费 `model_registry` 的唯一 Active 行。

## 4. 正式预测验收

| 项 | 结果 |
|---|---|
| Celery task | `task_937cf76d45d8`，queue=`project1_v212_a_core_p0`，execution_mode=`celery` |
| 状态序列 | API 实测 `PENDING(ACCEPTED) -> RUNNING -> SUCCESS` |
| run_id | `run_20260822T115159818317Z_5370682c70` |
| input_batch_id | `batch_v212_f86a148e14445db39cf41f6be03aa96b197f246b8a1c218c` |
| input_hash | `dd1bf5fed8aa806d0647546cd6c4d491bf423bb89853cafa413b3826ac89165c` |
| environment_hash | `97b3a004fdbc6f590953c02c087f1cfcfe5ff7186f5f910267c264aea00c48c6` |
| result_hash | `0f47756354980e97a7d8e0dd4577f43419e64b5c32d8bb748ba9f6968a6af993` |
| 结果 | 24 行、24 个不同小时、同一 run/input/model/feature、快照 24 行、半成品 0 |
| 来源 | 历史冻结业务特征，非模拟，时区契约 `America/New_York` |

重复 API 任务 `task_3015283d6c87` 返回同一业务 `run_id`；重复前后计数均为 runs/results/batches/snapshots=`1/24/1/24`，没有冲突事实。

## 5. 失败与回滚

| error_code | failed run | 结果行 |
|---|---|---:|
| `MISSING_FEATURE` | `run_20260822T112901647771Z_663646014c` | 0 |
| `ARTIFACT_HASH_MISMATCH` | `run_20260822T112901723169Z_bf44b0aa01` | 0 |
| `ACTIVE_MODEL_MISSING` | `run_20260822T112901729159Z_8900e9904c` | 0 |
| `INJECTED_ROW_12_FAILURE` | `run_20260822T112901733325Z_25ba7fa2b4` | 0 |

四条失败事实均为 `status=failed`、`record_count=0`；事务故障没有遗留输入批次或结果半成品。

## 6. 下游业务链

- 报告：`p5c_operation_decision_run_20260822T115159818317Z_5370682c70`，状态 `ready`。
- 策略：`p5d_1fc7290b124ca465a14528ed`，提交后由不同 reviewer 审核为 `approved`，审核记录 2 条。
- 预测、首页 context、报告、策略 evidence 均绑定同一 run、input batch、model、feature 与 historical 来源。
- 重复提交审核请求返回幂等；尝试发布返回 `stale_strategy_cannot_publish`，未伪造生产派发、交易收益或外部动作。

## 7. 回读与测试

- 专用 worker 停止并重新启动后，预测详情/结果、最新成功、原任务/重复任务、报告、策略、证据、审核、首页 context/overview 共 11 个 API 全部 200。
- 连续两轮页面/API 刷新前后计数保持 `1/24/1/1/2`，GET 无写副作用。
- 纠正 linked-worktree 资产根后，专项回归：`110 passed, 9 skipped, 1 deselected`。9 个 skip 均为未注入专用测试数据库 URL 的既有条件用例；本轮已另以本地 PostgreSQL 真实任务、失败注入、幂等、报告和策略链覆盖其核心门禁。
- AST 解析 11 个变更 Python 文件通过，`git diff --check` 通过。运行环境未安装 Ruff，因此未把 Ruff 作为验收项。
- 首轮聚合测试因未设置 `POWER_TRADING_ASSET_ROOT` 且 Day3 隔离数据库未启用而出现 fixture/error；修正测试环境后全绿。正式最终 worker 又在完全不设置该变量的进程中依靠 PostgreSQL 模型事实定位资产并成功生成新 run，证明实现不依赖测试修正。

## 8. 结论

`PREDICTION_ROOT_CAUSE_IDENTIFIED=YES`、`POSTGRES_MODEL_FACT=PASS`、`MODEL_HASH_CONTRACT=PASS`、`FEATURE_HASH_CONTRACT=PASS`、`FORECAST_TASK=SUCCESS`、`FORECAST_RESULT_ROWS=24`、`PARTIAL_RESULT_ROWS=0`、`IDEMPOTENCY=PASS`、`FAILED_ROLLBACK=PASS`、`PAGE_REFRESH_READBACK=PASS`、`RESTART_READBACK=PASS`、`PREDICTION_TO_STRATEGY_REPORT_CHAIN=PASS`、`FAKE_SUCCESS_COUNT=0`。

ChatBI Catalog 属于 C 所有权，A 未越界修改；依赖见 `A_TO_INTEGRATION_DEPENDENCIES.md`。
