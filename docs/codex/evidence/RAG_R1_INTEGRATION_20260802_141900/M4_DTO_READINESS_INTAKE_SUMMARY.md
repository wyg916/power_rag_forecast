# M4 公共 DTO 与迁移准备契约接收证据

## 接收边界

- 来源提交：`799f8dfa1c1570d2c848f433b3bd469d303cc7e1`。
- 来源包 5 个文件、净新增 511 行；含企业 DTO、静态 Alembic 图检查器、测试与 M4 原证据。
- 未接收候选支线的正式 Alembic revision，也未连接或修改数据库。

## Day 7A 基线适配

- 来源测试硬编码旧 head `0016_strategy_runtime`，当前基线唯一合法 head 为 `0017_day6_operational`。
- 仅把 2 个断言更新到 `0017_day6_operational`，并把过时 blocker `day4_7_head_not_frozen` 更名为事实准确的 `rag_r1_revision_not_created`。
- 未回退迁移、未降低单 head/线性图/无预占 revision/静态 AST 门禁。

## 验证与副作用

- 首次复验：8 passed、1 个旧 head 断言失败；适配后复验：`9 passed in 0.57s`。
- PostgreSQL DDL/DML、正式 revision、Qdrant、模型与网络写入：0。

## 回滚

使用普通 `git revert <M4-integration-commit>`；无外部状态需要恢复。
