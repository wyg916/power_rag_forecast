# PostgreSQL 0018 migration 实现与检查点证据

## 实现

- 新 revision：`0018_rag_enterprise_r1`，线性下接 `0017_day6_operational`。
- 新增/扩展企业文档、版本、Chunk、资产、ACL、Release、Release item、检索、Citation、QA 评测与 RAG 审计实体。
- 所有企业实体携带 `tenant_id`；release 固定 1024 维；release item 终态只允许 `published/isolated/duplicate/damaged`。
- 保留 legacy `kb_documents/kb_chunks` 数据和列，迁移不含 seed、Corpus 导入、全表删除或生产切换。

## 验证

- migration/static/固定目标 snapshot 单测：`13 passed in 1.70s`。
- Python compile 与 `git diff --check`：PASS。
- 只读数据库检查点：`E:\智能运营分析项目_备份\beta10d\20260802_150053709_RAG_R1_DB_PRE`。
- 目标：`localhost:5432/postgres` / `postgres`；Alembic `0017_day6_operational`；public structure SHA-256 `625a3a8aee3c461e82a7ba536e494d878b41e40a59dbeed3ac771937ebe70eab`。

## 并发漂移与停止边界

- 当前只读快照为 40 documents / 45 chunks；其中 34 / 39 在 14:35–14:38 由独立 `scripts/day8_rag_acceptance.py` 进程写入。
- 本包数据库写入 0，未执行 isolated replay 或 public upgrade；不会终止、覆盖或清理并发 Day8 数据。
- public upgrade 必须等并发进程退出并重新建立前置快照后才允许执行。

## 回滚

代码使用普通 `git revert <migration-implementation-commit>`；此包无数据库状态需要恢复。
