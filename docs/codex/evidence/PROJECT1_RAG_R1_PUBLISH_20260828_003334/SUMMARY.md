# PROJECT1 RAG-R1 正式发布与 Search 最终验收

- 任务：`PROJECT1_RAG_R1_VALIDATE_PUBLISH_SEARCH_FINAL_ACCEPTANCE`
- 时间：2026-08-27 23:23–2026-08-28 00:59（Asia/Shanghai）
- 分支：`main`
- 执行父提交：`65d95ee9275b99725596fbc951e0fad69af35cbb`
- 结论：`PASS`。`RAG-R1` 已完成 `validate → publish → PostgreSQL current → Qdrant Alias → Search/QA` 闭环，页面真实检索不再显示服务不可用。

## 安全配置

- 发布连接仅写入 Git 外本机配置 `E:\智能运营分析项目_本地配置\beta10d_day4_runtime.env` 的 `RAG_RELEASE_DATABASE_URL`。
- 目标身份经程序校验为 `postgres@localhost:5432/postgres`；本证据和仓库均未保存密码、完整 URL、令牌或 Qdrant Key。
- 原配置精确备份：`E:\智能运营分析项目_本地配置\beta10d_day4_runtime.env.pre_rag_release_20260827_232339.bak`。
- 发布前检查点：`backups/phase3/20260827_232339_RAG_RELEASE_PUBLISH_PRE/`。

## 发布链路

- 独立发布 Worker：回环地址 `127.0.0.1:8787`，最终 `healthy=true`，发布身份与 Web 读身份隔离。
- `validate`：HTTP 200，run `rag_publish_be07c12d24d5`，9/9 gates，45 documents、8,339 chunks、24 isolated、14 duplicates。
- `publish`：HTTP 200，run `rag_publish_c9688d22ab69`，`status=published`、`is_current=true`、`rolled_back_at=null`。
- PostgreSQL：`RAG-R1 / published / current=true / rag_chunks_RAG-R1`；审计存在 `validated`、`alias_manifest_saved`、`published` 成功事实。
- Qdrant：`rag_chunks_current → rag_chunks_RAG-R1`，8,339 points，strict mode 开启，dense 1024 与 `bm25-zh-v1` profile 一致，既有 snapshot 2 个保持不变。

## Search 故障闭环

1. 发布后首轮 Search 真实返回 `available=false / bm25_profile_unavailable`，证明数据库与 Alias 已成功但运行时 BM25 配置缺失。
2. 从当前发布数据库读取 8,339 个片段，校验 chunk 唯一性与逐条 `content_sha256` 后，按冻结的 `bm25-zh-v1` 算法重建不可变配置。
3. 重建结果：8,339 chunks、41 empty sparse chunks、50,844 vocabulary；profile SHA-256=`591f331717eb29b56a74a35d67ba88101046bae09d6e024a0bd5793d70edf6b0`，文件 SHA-256=`4f266825b56adba835e5b76dedbeaf5bec8f2bc2ba0340ba05fa2cf8e88cec16`。
4. 资产写入固定运行目录 `.runtime/rag/releases/RAG-R1/bm25_profile.json`；该目录为 Git 外可重建运行资产，不把大文件或凭据提交到仓库。
5. 仅重启属于最新主项目的后端，使其加载独立发布 Worker 客户端配置；认证、发布读取、RAG 健康均 HTTP 200。
6. 已发布版本再次校验返回 HTTP 409 `release_worker_conflict`，证明 Web 后端确已接通 Worker，并按状态机拒绝非法重复校验；不是 503 未配置。

## 实时功能验收

- `GET /api/knowledge/releases`：HTTP 200，current=`RAG-R1`，status=`published`。
- `GET /api/knowledge/health`：HTTP 200，status=`normal`，release=`RAG-R1`。
- Search：HTTP 200，`available=true`，release=`RAG-R1`，`enterprise_qdrant_hybrid`，reranker=`bge`，1 item / 1 citation。
- 重启后预热完成的热态 Search：1.469 秒。
- QA：HTTP 200，`available=true`、`passed=true`，1 item / 1 citation，0.730 秒。
- 正向批量 QA：2/2、100%，3.155 秒，两题均 high confidence。
- 宽泛“峰谷电价政策如何理解”返回跨领域候选时，Search 仍可用，但 QA 按领域一致性规则拒答；这是预期 fail-closed 负向验收。

## 自动化回归

- 发布 Worker、发布状态机、Qdrant transport/store、知识 API、鉴权与页面布局契约共 `105 passed in 17.19s`。
- 覆盖文件见 `test_summary.md`。
- Git secret 扫描与暂存差异检查在提交前执行，未发现本次密码、完整数据库 URL、Bearer token 或 Qdrant Key。

## 数据影响

- PostgreSQL 发生受控发布状态变更与审计写入：`RAG-R1` 从 `rolled_back/current=false` 变为 `published/current=true`。
- Qdrant 仅切换 Alias 到已经验收的 `rag_chunks_RAG-R1`；未重建/删除 collection，未删除 snapshot，point 数保持 8,339。
- 新增一个可重建的 Git 外 BM25 运行资产；文档正文、业务表、模型 Active 状态均未改。
- 发布 Worker 与后端保持运行，当前 Search 已预热。

## 回滚

- 发布状态回滚必须使用受控 Worker 的 `rollback` 动作，不直接改 `kb_releases` 或 Qdrant Alias；详细路径见 `rollback.md`。
- 外部发布配置可用发布前 `.bak` 精确恢复。
- BM25 文件属于可重建只读资产；只有在先停后端并确认回滚目标时，才允许按单文件路径移除或替换。

## 结论

用户指定的 `validate → publish → Alias/数据库/Search` 已全部打通。当前无发布或 Search 功能阻塞；仅保留本地 CPU 重启后首次双模型加载较慢这一运行注意项，不能把冷启动耗时隐瞒为热态性能。
