# Runtime RT3 Claim grounding 与内容安全接收证据

## 接收边界

- 来源提交：`fe29c8bd57135e8d0db8710d1aebefc1d2d5b347`。
- 接收 9 个文件、`+620/-11`；含 Claim grounding、内容安全、RAG 服务边界、AI context 最小接线、测试与 RT3 原证据。
- 未接收分支 merge、Alembic、Compose、主 Router 或正式模型配置。

## 验证与当前边界

- 内容安全、Claim/Citation 完整性、tenant/release 一致性与 hybrid 联合测试：`35 passed in 0.99s`。
- 无合格 Citation、证据污染、错误 locator 或 release 不一致时均 fail-closed。
- 测试基于 fixture；正式 Qdrant/数据库检索和 LLM 生成未发生。
- PostgreSQL、Qdrant、模型和网络写入：0。

## 回滚

使用普通 `git revert <RT3-integration-commit>`；无外部状态需要恢复。
