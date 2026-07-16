你正在处理“智能运营分析项目”。请严格遵守项目根目录 `AGENTS.md`、`docs/codex/PROJECT_BASELINE_SUMMARY.md`、`docs/codex/MASTER_ENGINEERING_RULES.md`，以及本任务文件。

执行要求：
1. 不重复全仓扫描，优先精确定位。
2. 任何修改前先建立任务级检查点并写入项目盘。
3. 不在 C 盘新增、删除或修改项目文件。
4. 不删除、批量移动或覆盖已有文件；需要时停止等待用户确认。
5. 回复保持简洁，完整证据写入 `docs/codex/evidence/`。
6. 遇到停止条件时不要变通，直接列出需要用户确认的事项。

# 任务：T003 — 闭合刷新、预测、同步的 run_id 原子事务链

## 目标
建立一次运行一个 `run_id` 的原子预测链，24 行预测与模型/特征/来源身份同事务入库；同 run 幂等，不同 run 共存，失败完整回滚。

## 前置门禁
T001、T002 已验收，存在经人工确认的唯一 Active。若未满足，停止并列出缺失前置条件。

## 范围
forecast_runs/forecast_results 结构、预测编排、同步仓储、事务、幂等、按 run 查询 API 和测试。不要开发报告/RAG/新模型。

## 强制要求
- 仅在隔离开发/测试库执行。
- 禁止无 WHERE 的 UPDATE/DELETE、TRUNCATE、DROP、先删后插、全表覆盖。
- 不删除旧 run、旧 artifact 或历史预测。
- 数据库迁移必须可 downgrade。

## 实施要点
1. run 记录包含状态、时间窗口、model/artifact/feature/schema、input_hash、result_hash、来源和错误信息。
2. `forecast_results` 建立 `UNIQUE(run_id, forecast_time)`。
3. 事务流程：创建 running→严格校验→写 24 行→数量/hash 校验→success→commit；任一步失败 rollback。
4. 同一 run 重试不重复；同输入新 run 可明确重放；旧批次共存。
5. 数据库为事实源，current 仅作为带 manifest 的可选导出缓存，页面不得直接绕过 API 读取。

## 验收测试
- 成功 run 正好 24 行。
- 同 run 重复执行仍是 24 行。
- 不同 run 并存，旧 run 不变化。
- 在写入第 1、12、24 行等位置注入失败，数据库无半成品。
- run 状态与结果数量一致。
- API 可按 run_id 和 latest_successful_run 查询。

## 输出
给出事务边界、幂等键、迁移结果、故障注入结果、旧批次共存证据和回滚步骤。
