# Ingestion I1 不可变源台账接收证据

## 接收边界

- 来源：`49935aaece4eeb27ac6e209d5531b16b15e31e0e`、`410bbdaab1a420383097851e502ce175bf8daee7`、`63b79abe044b76c7304f2928290d7673c352e562`。
- 接收 7 个文件、净新增 519 行；内容仅含 enterprise ledger、文件头识别、CLI、契约、测试和 I1 原证据。
- 未接收来源分支合并、Alembic、Router、Compose、权限/脱敏实现或运行态配置。

## 当前 83 文件只读核验

- 路径：`E:\智能运营分析项目\知识库`。
- 文件数：83；台账状态：ready 58、duplicate 14、quarantined 11。
- 隔离原因：受控转换 8、OCR 2、未知格式 1；内容重复 14。
- 确定性序列化 SHA-256：`ee61af9a0aa4509b2e7947e37c99004e2029fbfd69a55fe663e8acacafebf7d6`。
- 本阶段状态仍是准入状态，不冒充最终 `published/isolated/duplicate/damaged`。

## 验证与副作用

- `pytest tests/test_rag_enterprise_ledger.py -q`：`7 passed in 1.32s`。
- `git diff --cached --check`：PASS。
- PostgreSQL、Qdrant、模型、原始 Corpus、运行资产和网络写入：0。
- Candidate/Active/生产切换：NO。

## 回滚

使用普通 `git revert <I1-integration-commit>`；无外部状态需要恢复。
