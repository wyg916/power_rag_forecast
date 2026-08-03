# 并行工作树交接

共同精确基线：`ec78c569bd4036f23341e40b2d4d212a6f85177c`。

| 任务 | 分支 | 工作树 | 创建后状态 |
|---|---|---|---|
| OCR/VLM | `beta10d/rag-r1b-ocr` | `E:\智能运营分析项目_worktrees\beta10d_rag_r1b_ocr` | HEAD 精确一致、clean、任务边界存在 |
| 黄金集 | `beta10d/rag-r1b-golden-set` | `E:\智能运营分析项目_worktrees\beta10d_rag_r1b_golden_set` | HEAD 精确一致、clean、任务边界存在 |
| 检索性能 | `beta10d/rag-r1b-retrieval-performance` | `E:\智能运营分析项目_worktrees\beta10d_rag_r1b_retrieval_performance` | HEAD 精确一致、clean、任务边界存在 |

三条分支均禁止自行 merge、cherry-pick、rebase、数据库写入、发布、snapshot 或 alias/release 状态变更；完成后只向主控报告提交 SHA。
