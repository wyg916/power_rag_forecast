# RAG-R1 PostgreSQL 迁移与发布设计

## 1. 本包边界

本文件只冻结设计，不创建 Alembic revision，不执行 DDL/DML，不导入 Corpus。实际迁移必须位于 Day4–7 当前线性 head 之后，并在执行前取得人工确认。

## 2. 目标实体

### `kb_documents`

- 逻辑文档身份、`tenant_id`、归属域和审计时间。
- 不保存可变正文，不直接表示当前发布状态。

### `kb_document_versions`

- `version_id`、`document_id`、不可变源哈希、解析器/Schema 版本、有效期和解析终态。
- 同一租户与逻辑文档下，源哈希重复必须幂等复用或记录重复关系。

### `kb_chunks`

- 关联 `version_id`；保存父 Chunk、章节路径、页码、字符偏移、bbox、token 数、内容哈希和 Embedding 状态。
- Citation locator 必须能回读原版本内容；哈希不一致不得进入 Ready。

### `kb_assets`

- 保存图片、表格、公式、图表的类型、页码、bbox、内容哈希、OCR/VLM 结果和质量指标。

### `kb_access_policies`

- 保存租户、角色、用户和资源范围；拒绝客户端覆盖租户。

### `kb_releases` 与 `kb_release_items`

- 保存 Candidate、Validated、Published、Superseded、RolledBack 状态及不可变发布清单哈希。
- 一个租户最多一个 current Published release；Candidate 不得自动晋升。

### 检索、QA 与审计事实

- 扩展搜索和 QA 事实，记录租户、用户、Release、各阶段得分、Citation、延迟、评测结果、`run_id` 和 `trace_id`。
- QA confidence 统一采用数值字段；人类可读等级另设枚举字段，禁止字符串强转数值。

## 3. 约束与索引

- 所有业务表强制非空 `tenant_id`，当前值为 `default`。
- 文档版本、Chunk、资产、ACL 和 Release item 的外键不得跨租户。
- 对 `tenant_id + release/status/effective time`、文档版本、父 Chunk、内容哈希、审计 ID 建立索引。
- 不直接删除旧表或旧列；兼容读取期结束后再由用户确认归档清理。
- Qdrant payload 字段与 PostgreSQL Release 清单字段必须一一映射并保存 profile/hash。

## 4. 迁移执行门禁

1. 验证目标只能是本机 `localhost:5432/postgres`、用户 `postgres`。
2. 建立 schema-only 和关键事实指纹检查点。
3. 在空隔离 Schema 执行 `upgrade → downgrade → upgrade`。
4. 比较两次 head 的逻辑 Schema hash，验证 downgrade 无残留。
5. 人工确认后才在当前 PostgreSQL 执行 upgrade。
6. 导入数据、构建 Candidate 和发布分别再次确认，不与 migration 隐式绑定。

## 5. 两阶段发布

1. Candidate Collection 完成索引、门禁和快照；保存 alias 映射。
2. 原子切换 Qdrant alias 到 Candidate。
3. 更新 PostgreSQL current release。
4. PostgreSQL 更新失败时立即切回旧 alias。
5. 运行关键问题、ACL、健康和 Citation smoke。
6. 成功后旧 Release 标记 Superseded；旧 Collection 仅归档，不删除。

## 6. 回滚

- 目标：RTO 不超过 5 分钟，RPO 为 0。
- 回切 alias、恢复 PostgreSQL current release、清理 release-aware 缓存。
- 数据库 migration、Qdrant snapshot、配置和代码分别维护回滚步骤。
- 不执行批量删除、全表更新、DROP 或 TRUNCATE；旧事实保留到用户另行确认。
