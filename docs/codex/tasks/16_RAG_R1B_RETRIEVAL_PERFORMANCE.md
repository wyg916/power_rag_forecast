# RAG-R1B 并行任务：检索性能闭环

## 目标

在不降低 Recall、MRR、critical 和 citation 门禁、不启用 fallback 的前提下，把包含 BGE reranker 的正式端到端检索 P95 从 `6175.825ms` 降至 `<=1500ms`。

## 工作线

- 分支：`beta10d/rag-r1b-retrieval-performance`
- 工作树：`E:\智能运营分析项目_worktrees\beta10d_rag_r1b_retrieval_performance`
- 精确基线 HEAD：由主控最终交接矩阵公布；开始前必须 `git rev-parse HEAD` 精确一致。

## 允许修改范围

- `backend/app/services/hybrid_retrieval_service.py`
- `backend/app/services/rerank_service.py`
- `backend/app/services/rag_qdrant_transport.py`
- `backend/app/services/qdrant_vector_store.py`
- `scripts/rag_r1_candidate_acceptance.py`
- `tests/test_rag_enterprise_hybrid_core.py`
- `tests/test_rag_qdrant_transport.py`
- `tests/test_rag_qdrant_vector_store.py`
- `tests/test_rag_r1_candidate_acceptance.py`
- `tests/performance/rag_r1_retrieval_*`（允许新增）
- `docs/codex/evidence/RAG_R1B_RETRIEVAL_PERF_*`（仅本任务证据）

## 禁止范围

- 不得修改黄金题文件、OCR 文件、PostgreSQL、迁移、公共配置、Compose、公共 API 契约。
- 不得创建 snapshot、切换 alias、修改 release 状态、发布或生产切换。
- 不得通过跳过 reranker、缩小正式题集、只报告 hybrid core、降低阈值或复用旧结果制造 PASS。
- 不得 merge、cherry-pick、rebase 或直接合入主控。

## 交付门禁

- 正式 50 题端到端 P95 `<=1500ms`；同时 R@3 `>=90%`、R@5 `>=98%`、MRR `>=85%`、critical `100%`、citation `100%`。
- 报告冷启动、稳定态、P50/P95、hybrid 与 reranker 分段耗时，固定硬件/线程/batch/model hash。
- GET/search 仍零写入、无 fallback、错误 fail-closed；定向测试与幂等复跑通过。
- 只提交本任务允许文件，并向主控报告提交 SHA；不得自行合并。

