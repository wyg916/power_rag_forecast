# Ingestion I3 分块与引用定位接收证据

## 接收边界

- 来源：`56b6575a9caf8801857a97615f9b37b75e0b2710`、`792ee536e45dad10b4a5a455cd50bd3ca667dc68`。
- 接收 11 个文件、净新增 768 行；仅含父子分块、引用定位、冻结导出、质量门禁、测试及 I3 原证据。
- 修复确保逻辑表格不被误记为二进制资产。
- 未接收分支 merge、Alembic、Router、Compose 或正式运行资产。

## 验证与副作用

- 分块、引用、质量、XLSX 联合测试：`11 passed in 1.98s`。
- `git diff --cached --check`：PASS；敏感扫描在提交前执行。
- PostgreSQL、Qdrant、原始 Corpus、Candidate 资产、模型和网络写入：0。
- 此包只证明确定性算法契约，不代表 83 文件 Candidate 已构建。

## 回滚

使用普通 `git revert <I3-integration-commit>`；无外部状态需要恢复。
