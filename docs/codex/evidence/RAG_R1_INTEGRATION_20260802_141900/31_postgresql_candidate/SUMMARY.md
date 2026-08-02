# RAG-R1 PostgreSQL Candidate 元数据修复与闭环

- 状态：`PASS`（仅 Candidate 元数据；未发布、未切 alias）。
- 目标：`localhost:5432/postgres`，用户 `postgres`；事务 `READ ONLY`；Alembic `0018_rag_enterprise_r1`。
- public structure SHA-256：`15d4fd97a193c57b6b3bc0b6ad484902be2463cce3048fd3cb8fecd7b7e208be`。
- 发现数据库已存在 `default/RAG-R1` Candidate：`is_current=false`，Collection `rag_chunks_RAG-R1`。
- 精确对账：45/45 documents、45/45 versions、8,339/8,339 chunks、83/83 release items；ID missing/extra 均为 0，逐字段 mismatch 均为 0。
- Release items：45 `published`、14 `duplicate`、24 `isolated`，Chunk 合计 8,339，Asset 0。
- Source ledger SHA-256 一致：`ee61af9a0aa4509b2e7947e37c99004e2029fbfd69a55fe663e8acacafebf7d6`。
- 唯一偏差：`kb_releases.manifest_sha256` 当前为 Candidate artifact SHA-256 `f74a29af786e03a945dd7955757c5ac352ebb4a15baae7138f14281886ad8426`；冻结契约 `candidate_manifest_sha256` 应为 `2aeaeb8325a192a8acceeee2dd81c631c313c40b0d7be6333bfd512fd52a0282`。
- 影响：Release API/一致性门禁无法把 PostgreSQL Release 与冻结 Candidate manifest 建立同一哈希事实，继续集成必须 fail-closed。
- 控制台中文显示异常经逐字段程序比较排除：数据库标题、正文、Citation locator 均与 UTF-8 Candidate 精确相等，并非持久化乱码。
- Qdrant Candidate、alias、snapshot、Published/生产状态均未被本审计改变。

## 已授权修复结果

- 新增 `scripts/rag_r1_candidate_database.py`，支持冻结目标守卫、全量新装导入、既有 Candidate 精确校验、单行 compare-and-swap 修复、事务回滚探针和幂等复跑。
- 事务回滚探针：PASS；条件更新后主动 rollback，旧哈希完整恢复，持久写入 0。
- 正式事务：`kb_releases` 精确更新 1 行；追加 `candidate_manifest_reconciled` 审计 1 行；合计写入 2。
- 幂等复跑：PASS；更新 0、审计新增 0、数据库写入 0。
- 最终只读验证：45/45 documents、45/45 versions、8,339/8,339 chunks、83/83 release items，missing/extra/field mismatch 全部为 0。
- 最终 manifest SHA-256：`2aeaeb8325a192a8acceeee2dd81c631c313c40b0d7be6333bfd512fd52a0282`。
- 前后 public structure SHA-256 完全一致；仅 `kb_releases` 与 `kb_rag_audit_events` 两张预期表指纹变化，其他表 0 变化。
- 定向回归：31 passed；py_compile PASS。

## 修复实现范围

1. `rag_r1_candidate_database` 工具固化全量 Candidate 导入、精确校验、幂等和事务回滚，不依赖临时脚本。
2. 单行修复带旧值、`status=candidate`、`is_current=false` 前置条件；任一漂移 fail-closed。
3. post-write snapshot：`post_write/public_database_snapshot.json`，SHA-256 `cd1193906e0e0546148469b3b980100c9170807cb2e6d5a804a77c52945f4a5a`。

## 回滚

- 代码：对修复包提交执行 `git revert <commit>`。
- 数据库：以 `pre_write/public_database_snapshot.json` 为前置事实；若修复已提交，使用相同主键和新值前置条件把 `manifest_sha256` 恢复为 `f74a29af…ad8426`，`updated_at` 恢复为 `2026-08-02 20:21:32.327227+08:00`，并追加回滚审计事件；不删除文档、Chunk、Release item 或历史审计。
- 快照：`pre_write/public_database_snapshot.json` SHA-256 为 `55b5dd7b13d3146fe7517cf2f6fb89560f0dfc0ce70e604cb04b23daaea4b846`。
