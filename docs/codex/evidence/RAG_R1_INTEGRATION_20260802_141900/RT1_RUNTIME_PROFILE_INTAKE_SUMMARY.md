# Runtime RT1 企业运行 profile 接收证据

## 接收边界

- 来源：`0efc44d3ea1a5f7ebdf4cf8b79f4616423038752`、`0bc7a44467147f9e65c74fa4923a614275788a13`。
- 接收 7 个文件、`+724/-23`；含 embedding/rerank/health 企业 profile、运行契约、测试和 RT1 原证据。
- 未接收分支 merge、公共 Compose、Alembic、Router 或正式环境配置。

## 验证与当前边界

- 企业 profile 与 P3 health 一致性测试：`25 passed in 0.90s`。
- 明确拒绝 256 维、未知模型、Hash embedding、heuristic rerank、文件 fallback 与版本不匹配。
- 当前只证明配置门禁；模型权重尚未反序列化，真实 embedding/reranker 健康仍未建立。
- PostgreSQL、Qdrant、模型和网络写入：0；生产切换：NO。

## 回滚

使用普通 `git revert <RT1-integration-commit>`；无外部状态需要恢复。
