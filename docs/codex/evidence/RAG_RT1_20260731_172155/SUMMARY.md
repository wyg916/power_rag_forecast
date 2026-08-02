# RAG-RT1 证据摘要

## 范围

- 工作树：`E:\智能运营分析项目_worktrees\rag_enterprise_runtime`
- 分支：`codex/rag-enterprise-runtime`
- 修改前检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_171035_RAG_RT1_PRE`
- 交叉审查修正检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_172900_RAG_RT1_REVIEW_PRE`
- 数据库、Repository、API、公共配置、Alembic、前端变更：0
- 网络、依赖下载、Qdrant、生产模型加载、数据库连接：0

## 实施结果

- 新增 `RetrievalContext`、`EmbeddingProfile`、`ReleaseIdentity`、`CitationLocator` 和统一运行时状态契约。
- `RAG_PROFILE=enterprise` 或生产环境强制 BGE Large 1024、BGE reranker、固定 release/collection/alias。
- 未知 Provider、模型、维度、Release、模型目录或任何 Hash/启发式/文件 fallback 配置均 fail-closed。
- Embedding 与 reranker 均强制 actual version/expected version 非空且精确相等；缺失或不一致返回稳定 issue code。
- Enterprise Embedding 失败返回空向量与 unavailable 元数据，不再进入 Hash fallback。
- Enterprise rerank 失败返回空候选，不再进入 heuristic/hybrid-score fallback。
- `rag_health()` 默认返回公共脱敏视图；`rag_health(diagnostic=True)` 仅返回脱敏诊断，不包含本地模型完整路径或密钥。
- 非 Enterprise 的开发兼容路径保持原行为。

## 测试

1. `pytest tests/test_rag_enterprise_runtime_contract.py tests/test_p3_rag_docker_consistency.py -q`
   - 交叉审查修正后 25 passed。
2. `pytest tests/test_phase5_rag_recovery.py tests/test_phase5_a1_rag_contract.py tests/test_rag_hybrid.py -q -k 'not test_rag_search_merges_keyword_vector_and_reranks'`
   - 33 passed，1 deselected。
3. `pytest tests/test_knowledge_business_api.py -q`
   - 3 passed。
4. E 盘隔离临时目录下合并复跑以上测试：
   - 交叉审查修正后 61 passed，1 deselected。
5. 扩展回归中的 `test_rag_search_merges_keyword_vector_and_reranks` 仍失败；已在未包含本包变更的主工作树复跑并得到相同结果。既有测试候选缺少 domain，被现有 `_domain_consistent_items` 清空，不属于 RAG-RT1 范围。
6. `git diff --check`
   - 通过，仅有 Git 的 LF/CRLF 工作区提示，无 whitespace error。

## 回滚

- 提交后优先使用 `git revert <RAG-RT1提交哈希>`。
- 提交前可按检查点 `RESTORE.md` 对照 `critical_hashes.csv`，逐个恢复本包文件。
- 禁止 hard reset、clean、递归删除或覆盖无关工作。

## 未完成项

- Qdrant 客户端、混合检索、tenant/ACL 请求上下文注入、API 诊断权限和正式发布一致性由后续任务包/主线完成。
- 本包只验证配置与目录准入，不加载或验证模型二进制内容。
