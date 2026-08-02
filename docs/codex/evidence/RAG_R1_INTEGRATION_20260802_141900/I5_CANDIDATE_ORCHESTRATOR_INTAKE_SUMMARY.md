# Ingestion I5/I5A Candidate 调度接收证据

## 接收边界

- 来源：`8ed99cae74361905ebe874963eed5810f0bcd330`、`0d24fdc3009325b763b1e6df5b0724082c2e6af9`。
- 接收 4 个文件、净新增 863 行；仅含 Candidate 调度器、测试及 I5/I5A 原证据。
- 未接收来源分支 merge、数据库迁移、Router、Compose 或正式运行资产。

## 验证与副作用

- Candidate 确定性、冻结 manifest、逐文档隔离、已知/未知程序错误 fail-closed：`17 passed in 0.85s`。
- `git diff --cached --check`：PASS；敏感扫描在提交前执行。
- 测试使用注入 fixture，不是 83 文件正式 Candidate 成绩。
- PostgreSQL、Qdrant、Corpus、Candidate 资产、模型和网络写入：0。

## 回滚

使用普通 `git revert <I5-integration-commit>`；无外部状态需要恢复。
