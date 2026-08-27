# PROJECT1 知识库功能链路恢复证据

- 任务：`PROJECT1_KNOWLEDGE_BASE_FUNCTIONAL_RECOVERY`
- 时间：2026-08-27 16:58–20:51（Asia/Shanghai）
- 分支：`main`
- 最终父提交：`8ea13edfcda7e415bf0f708c2b457e4f8678bc09`
- 结论：`PARTIAL`。文档列表、详情、上传既有文本白名单、导出、重建索引、刷新 Embedding、单文档重新索引、任务队列和权限矩阵已接通；RAG 检索/批量 QA/发布仍被唯一的本机 PostgreSQL 发布身份门禁阻断，未伪造成功。

## 根因与修复

1. 统一启动器只启动健康/预测 Worker，没有消费 `rag,embedding,report` 的知识 Worker，导致索引与向量按钮提交后没有正确执行者。
2. 正式 PostgreSQL 仅 39/8378 个官方片段有向量；现已通过同版本本地 BGE 任务和只读 Qdrant `RAG-R1` 向量事实源补齐为 8378/8378，1024 维、正式 provider/model/version、fallback 0。
3. “重新索引”原来误触发全库任务；新增租户校验后的文档级重新索引 API 和前端绑定。
4. 发布 API 需要独立 Worker；新增回环地址、独立 Bearer token、Qdrant admin 隔离和受控启停。控制器只接受 `localhost:5432/postgres` 的 `postgres` 发布身份，普通 `beta10d_app_login` 会 fail-closed。
5. 运行档由 candidate 目标改为 `production_alias`；在 PostgreSQL current fact 与 Qdrant alias 尚未同时发布前，检索保持不可用。

## 实时数据与服务验收

- PostgreSQL 官方向量：`8378/8378`，维度 1024；正式 embedding profile 不一致：`0`。
- 初次向量恢复任务：`task_dc3a24b76b44`，最终 `success / 100%`。
- “重建索引”：`task_3b10d8613725`，`success / 100%`。
- “刷新 Embedding”：`task_af42565c6cfa`，`success / 100%`。
- 单文档“重新索引”：`task_e7d7732125d1`，`success / 100%`。
- Knowledge Worker：`knowledge-worker@wyg_win11`，队列 `rag,embedding,report`，Redis connected。
- `GET /api/knowledge/health`：HTTP 200，`status=normal`，fallback 0。
- 文档列表：HTTP 200，79 份；导出：HTTP 200，CSV 11037 bytes。
- `RAG-R1`：`rolled_back / is_current=false`；Qdrant `rag_chunks_current` alias 为 NULL。
- 检索：HTTP 200 且 `available=false`，原因 `published_release_fact_mismatch`。
- 批量 QA：HTTP 200，1 项、0 通过；这是发布未完成时的真实失败结果。
- 发布校验：HTTP 503，`release_worker_unavailable`。
- 数据库权限核对：`beta10d_app_login` 对 `kb_releases` 仅 SELECT、无 INSERT/UPDATE/DELETE；`beta10d_security_login` 也无发布权限；未发现获批的 `RAG_RELEASE_DATABASE_URL` / `MIGRATION_DATABASE_URL` 或可用本机 postgres 口令。

## 自动化验证

- 后端/RAG/权限/队列专项：`125 passed in 31.17s`。
- 最新启动器/权限矩阵/知识 API 复测：`35 passed in 224.98s`。
- 权限矩阵生成：208 个方法+路径、192 个唯一路径、201 个受保护路由。
- Python 编译：PASS。
- 前端 `npm run build`：PASS，3689 modules transformed。
- 浏览器验收连接多次超时，未据此声明 UI 交互闭环；按钮结论以真实 API、任务终态、前端构建和契约测试为准。

## 数据影响与回滚

- Qdrant 仅执行只读 scroll；未创建/删除 collection、snapshot 或 alias。
- PostgreSQL 更新派生索引字段 `kb_chunks.embedding_json/metadata_json`，并留下任务、审计和 QA 失败记录；未删除业务数据、未修改文档正文。
- 代码回滚：对本任务提交执行 `git revert <commit>`。
- 向量属于可重建派生索引，代码回滚不要求清除；如必须恢复旧索引状态，应先停知识 Worker，并由数据库管理员依据本检查点与 Qdrant `RAG-R1` 重新生成，禁止直接批量清空正式表。
- 检查点：`backups/phase3/20260827_165829_KNOWLEDGE_FUNCTIONAL_RECOVERY_PRE/`。

## 唯一剩余门禁

在本机安全配置中提供一次 `RAG_RELEASE_DATABASE_URL`（或 `MIGRATION_DATABASE_URL`），目标必须是 `postgresql+psycopg://postgres:<redacted>@localhost:5432/postgres`。随后由受控 Worker 依次执行 `validate -> publish`，验收 PostgreSQL `is_current=true`、Qdrant alias 指向 `rag_chunks_RAG-R1`、真实检索与批量 QA 通过。当前未获得该凭据，因此不能诚实标记“全部打通”。
