# RAG-R1 旧旁路封口

- 结果：`PASS`。
- 企业入口：`rag_search` 只进入注入式 Qdrant enterprise path；旧 PostgreSQL keyword/vector、文件检索和知识统计函数不可触达。
- Embedding：企业 profile 先执行完整 Runtime Contract；Hash provider 与 Hash fallback 不可触达，失败返回 unavailable。
- Reranker：企业 profile 失败返回 unavailable，不进入 heuristic 或 hybrid-score fallback。
- 文件 fallback：企业 Runtime Contract 对任何启用值 fail-closed；Candidate/Published 查询不读取项目文件。
- 模型加载：Embedding 与 Reranker 强制 Hub offline、禁用遥测、`local_files_only=true`、`trust_remote_code=false`；Reranker 强制 Safetensors。
- Seed：GET/Search 没有 seed 调用；`ensure_seed_knowledge` 默认 `explicit=false` 时阻断，RAG-R1 企业路径不调用该函数。
- 验证：legacy bypass、runtime contract、hybrid core、Qdrant security 共 38 passed。
- 保留边界：旧类仅为非 enterprise 兼容代码存在，不属于 RAG-R1 可达调用图；本包不扩大到无关旧模块删除。

## 回滚

执行 `git revert <本包提交>`；本包没有数据库、Qdrant 或模型资产写入。
