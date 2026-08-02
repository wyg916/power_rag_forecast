# RAG-RT5 企业应用编排证据

## 范围与检查点

- 基线：`5a75c0568bd131337f9b353bacdee9124f125eb1`。
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_185951_RAG_RT5_PRE`。
- 仅新增 M5 API seam 的注入式应用编排、端口协议、纯 Fake 测试和本证据。

## 实现结果

- Draft ingestion 强制“不可变内容先写、Draft 事实后原子创建”。
- tenant、idempotency key 与内容/request hash 共同约束重试；同请求返回同一事实，同 key 异 hash 冲突。
- ingestion 状态读取与 release 列表只调用只读事实端口。
- Candidate 创建及 validate/publish/rollback 通过注入 publisher，严格校验状态、身份、tenant、run/trace 和 DTO。
- content/fact/publisher 故障、跨 tenant、异常端口返回均 fail-closed。
- 默认 `get_enterprise_knowledge_application()` 未改动，生产仍为 unavailable；测试 Fake 不作为正式持久层。

## 验证

- RT5 编排专项：`10 passed in 0.23s`。
- RT5 与 M5 API seam 联合回归：`20 passed in 1.42s`。
- 全部 RAG enterprise 专项回归：`156 passed in 13.12s`。
- Python `compileall`：PASS；`git diff --check`：PASS。
- 变更共 3 个文件、低于 900 行新增预算。

## 外部影响与回滚

- 未连接或写入真实文件、PostgreSQL、Qdrant、队列、缓存、模型或网络。
- 未修改 Compose、Alembic、正式 release、alias、Collection 或生产依赖装配。
- 回滚使用 `git revert <RAG-RT5-commit>`；没有外部状态需要恢复。
