# PROJECT1 v2.12.0 Prediction E2E Report

## Round 1 正式运行

- run_id：`run_20260822T190147191292Z_04ced065c8`
- 状态链：`ACCEPTED → RUNNING → SUCCESS`
- 结果行数：`24`
- 唯一小时：`24`
- partial 行数：`0`
- fake success：`0`
- idempotency：`PASS`
- failed rollback：`PASS`
- refresh/task readback：`PASS`
- worker restart persistence：`PASS`
- downstream chain：`prediction → dashboard → strategy → report → review/publish boundary`，`PASS`

## 事实与血缘

运行使用 PostgreSQL 模型事实和冻结的真实业务输入快照；`is_simulated=false`，没有 Mock、Demo、历史预测复制或 fallback。预测、dashboard、strategy 与 report 保持相同 run_id、input batch、model/version 与 feature identity。

策略审核记录已形成，但历史/过期结果的 publish 被边界正确阻断；这属于 fail-closed 验收，不是生产发布。

## 失败门禁

以下场景均明确失败且不落 partial success：缺特征、额外特征、特征顺序错误、dtype 错误、timezone 错误、schema/feature hash 错误、Active model 不存在、row 12 中途故障、唯一键冲突、legacy/fallback 路径。GET/readback 不产生 seed、激活或同步副作用。

## ACL 与审计闭环

- `audit_logs.id` 默认序列权限已按最小权限修复。
- runtime 合法审计 INSERT PASS；非法/越权写入仍拒绝。
- 预测事实输入表仅授予运行链所需的最小只读权限。
- 审计脚本连续执行幂等，role attributes 无危险权限，schema 无非预期变化。

## 证据

- `round1_prediction_evidence_4a108ce.json`
- `round1_prediction_submit_4a108ce.json`
- `round1_prediction_poll_4a108ce.json`
- `round1_prediction_idempotent_submit_4a108ce.json`
- `round1_restart_readback_4a108ce.json`
- `round1_post_acl_chain_4a108ce.json`
- `round1_prediction_contract_gates_44e048d.xml`
- `round1_prediction_transaction_gates_44e048d.xml`
- `round1_prediction_failure_gates_44e048d_guard.json`

Round 2 必须新建正式预测运行，不复用本 run_id 作为最终 SAME-SHA 结果。
