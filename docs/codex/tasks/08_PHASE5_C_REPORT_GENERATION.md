# PHASE5-C 报告生成闭环

## 目标

把已通过的预测事实链、模型事实链和 AI/RAG 来源契约组合为可自动生成、可追溯、可审核的运营决策报告。报告只提供决策支持，不执行交易，也不进入 PHASE5-D 策略状态机。

## 子阶段

1. `C1`：正式数据库备份、迁移验证、正式升级、模型准入与正式预测。
2. `C2`：报告构建、文件落盘、`report_runs` 原子持久化、API/任务链修复。
3. `C3`：幂等、失败回滚、读取无副作用、审核边界、浏览器和完整回归。

每个子阶段必须保留检查点、结果证据和 PASS 门禁；失败不得进入下一阶段。

## 报告事实契约

- 必须绑定真实存在且状态为 `success`、结果恰好 24 行的 `run_id`。
- 必须记录 `model_version`、`feature_version`、`schema_hash`、`result_hash`、来源类型和生成时间。
- 报告数值只能来自该 run 的 `forecast_results`，不得由 LLM 补写。
- 报告必须包含预测摘要、关键时段、风险提示、运营建议、证据和限制说明。
- 过期预测可以生成审计报告，但必须显式标记 stale，且禁止表述为当前实时交易依据。
- 报告建议不得描述为自动交易指令或已实现收益。

## 写入与读取边界

- 只有显式生成操作可以写 `report_runs` 和报告文件。
- GET、列表、详情、下载和 AI 报告查询不得生成或更新报告。
- 同一 `run_id + report_type` 重复生成必须幂等，不得重复落库或覆盖不同事实。
- 生成失败不得留下 `ready` 半成品记录；数据库事务失败时应清理本次新建文件。
- 审核、发布必须继续使用显式权限与审计日志，生成报告不得自动发布。

## PASS 门禁

1. 正式库升级路径先在克隆库完成 upgrade/downgrade/re-upgrade，随后正式库升级成功。
2. 模型完成 Candidate→Validating→Validated→Active，身份与 Artifact hash 全部匹配。
3. 正式预测 run 为 success、24 行、结果 hash 可复核。
4. 报告绑定正式 run，结构、文件、数据库记录和证据一致。
5. 重复生成幂等；故障注入无半成品。
6. 报告读取 100 次无写副作用。
7. stale、source_type、run_id、模型/特征版本和限制说明正确。
8. 相关 Python、T001–T005、A/B、TypeScript、Vite、FastAPI/PostgreSQL 与浏览器回归通过。
9. Artifact 未修改，敏感信息未写入仓库或证据，Manifest 错误为 0。
10. Git 提交与普通推送成功；禁止强推。

## 回滚

- 代码回滚到 `PHASE5_AB_BASELINE_FREEZE` 远端锚点。
- 正式数据库使用 PHASE5-C 前的 full dump 恢复；优先恢复到新数据库核验。
- Active 可通过显式 `deactivate_model` 回退；不得直接无条件更新全表。
- 报告记录和文件保留审计，不进行批量删除。
