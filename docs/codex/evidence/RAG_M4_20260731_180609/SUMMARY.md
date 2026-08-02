# RAG-M4 证据摘要

- 范围：Enterprise ingestion/release/ACL/asset/Citation/retrieval/QA/error DTO 与 JSON Schema；Alembic 静态就绪审计。
- DTO 全部 `extra=forbid`；客户端 ingestion/release 请求不含 `tenant_id`，服务端事实强制 `tenant_id=default`。
- Citation 强制版本、发布、页码/章节、字符偏移、bbox、asset、quote 与 SHA-256 字段；QA `confidence` 拒绝字符串。
- Alembic 只通过 AST 读取 `revision/down_revision`，不导入迁移模块、不连接数据库。
- 当前观察到单线 head `0016_strategy_runtime`；未预占下一 revision，直到 Day4–7 head 冻结。
- `planned_revision=None`，阻塞项包含 `day4_7_head_not_frozen` 与 `migration_execution_confirmation_required`。
- DTO 与静态迁移审计定向测试：`9 passed`；Python 语法与 `git diff --check` 通过。
- 规模：5 文件，低于 8 文件/700 行门禁。
- 未创建 Alembic revision，未执行 DDL/DML，未访问 PostgreSQL、Qdrant、网络、模型或依赖。
- 回滚：正常 `git revert` 本包提交；无外部数据恢复动作。
