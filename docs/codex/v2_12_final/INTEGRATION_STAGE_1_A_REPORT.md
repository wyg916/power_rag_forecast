# PROJECT1 v2.12.0 Integration Stage 1 / A 报告

## 结论

- `STATUS=PASS`
- `PRE_MERGE_SHA=61204f48a870e36742fed8c5fb407dc9c6e7e55b`
- `A_SHA=3aa38348d5822f69c21dd8aee93a6ac0ade00001`
- `POST_A_MERGE_SHA=814bf633d09853b7e29d13c8734399fc9e4cfb05`
- 合并方式：`git merge --no-ff codex/project1-v2.12.0-core-p0`
- 冲突：仅 `docs/codex/TASK_STATUS.md`；逐段保留 Bootstrap 与 A 两侧记录后移除冲突标记，未使用 ours/theirs。

## 预集成门禁

- Integration worktree 路径、分支、HEAD 与 clean 状态符合指令。
- `3b6eb33df96ece08a60acce802d6ec249ec5a826` 是 `61204f48a870e36742fed8c5fb407dc9c6e7e55b` 的祖先。
- 两者差异仅 Bootstrap 的状态、manifest、审计和证据文档，无业务代码、接口契约或测试基线漂移。
- A worktree HEAD 精确等于 A SHA 且 clean；A 报告中的 SUCCESS/24/0 partial、幂等、失败回滚、重启读回、下游链与 fake success=0 均核验通过。

## Integration SHA 定向回归

- PostgreSQL Active model fact：唯一 Active；run 的 model/feature/schema/artifact identity 与其一致。
- 正式 Celery 任务：`task_932b3a30cc4b`，状态序列 `PENDING/ACCEPTED -> RUNNING -> SUCCESS`。
- prediction run：`run_20260822T142807620068Z_ed7f7a4549`。
- input batch：`batch_v212_4f6dcf63048d881668e6f89a810d5ec4c2675b90c484e7fc`。
- 结果证据：`forecast_results=24`、distinct forecast hour=24、partial=0、input snapshots=24、input batches=1。
- 幂等复投：`task_148967f463f0` 返回同一 run，复投前后 run/result/batch/snapshot 计数不变。
- 失败回滚：`MISSING_FEATURE`、`ARTIFACT_HASH_MISMATCH`、`ACTIVE_MODEL_MISSING`、第 12 行注入失败均为 failed run 且结果行数为 0；既有 SUCCESS run 保持 24 行。
- API/task readback：run detail、24 results、原始 task 与幂等 task 均为 200/正确终态。
- restart persistence：停止本轮专用 worker 后，以相同专用队列启动新 worker，再次读取 run/task/report/strategy 均通过；随后仅停止该专用 worker。
- downstream：report `p5c_operation_decision_run_20260822T142807620068Z_ed7f7a4549` 为 ready；strategy `p5d_cfe35ceb40bb5c1b54d69115` 经 submit、同请求幂等 submit、独立 reviewer approve，审计 review=2；historical/stale publish 被 `stale_strategy_cannot_publish` 正确阻断。

## 测试

- A 定向非 integration 组合：`102 passed, 28 skipped, 1 deselected`；同时有 24 个 setup error，全部来自 linked worktree 缺少 Git ignored 模型资产。
- 按 A 已冻结的本地环境契约设置 `POWER_TRADING_ASSET_ROOT=E:\智能运营分析项目` 后，唯一失败文件 `tests/test_t002_safe_model_contract.py` 为 `26 passed`。
- 合并计算：实际通过 128，跳过 28，deselected 1；环境前置错误已显式保留，不计作一次性 PASS。
- 11 个 A 变更 Python 文件 AST parse PASS；`git diff --check` PASS。

## 范围与停止点

- B 未合入；C 未合入；main 未更新；Tag 未创建。
- 未修改普通根目录，未终止未知 8000/5173 实例，未切生产、未激活模型。
- Stage 1 完成后停止，等待 C `READY_FOR_INTEGRATION=YES`。
