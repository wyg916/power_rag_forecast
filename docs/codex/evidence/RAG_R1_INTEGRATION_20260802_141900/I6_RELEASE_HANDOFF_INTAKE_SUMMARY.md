# Ingestion I6 Candidate 发布交接接收证据

## 接收边界

- 来源提交：`4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227`。
- 接收 4 个文件、净新增 630 行；仅含 Candidate release envelope、sink receipt 校验、测试、依赖声明与 I6 原证据。
- 未接收分支 merge、数据库迁移、Router、Compose 或正式 sink 配置。

## 验证与副作用

- envelope 确定性、83 条 ledger 约束、schema/count/hash 篡改、跨 tenant/profile、sink receipt 与异常脱敏：`11 passed in 0.77s`。
- `git diff --cached --check`：PASS；敏感扫描在提交前执行。
- 测试 sink 为内存 fixture，不代表 PostgreSQL/Qdrant 双写完成。
- PostgreSQL、Qdrant、Corpus、模型和网络写入：0；Candidate/Active/生产切换：NO。

## 回滚

使用普通 `git revert <I6-integration-commit>`；无外部状态需要恢复。
