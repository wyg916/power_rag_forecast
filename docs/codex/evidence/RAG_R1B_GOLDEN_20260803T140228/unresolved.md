# 尚未闭环事项

1. 人工审批：Retrieval 50 题与 AI 100 题共 150 题均为 `approval_status=pending`、`human_verified=false`，annotator/reviewer 尚未分配。
2. AI 精确证据映射：90 题要求 Citation；其中 78 题无 document ID，22 题仅有未核验 legacy `kb_` 候选，100 题均无 RAG-R1 version/chunk ID。现有工作树没有可把 29 个 AI 标题别名可靠映射到 RAG-R1 immutable manifest 的完整资产，禁止自动伪填。
3. Retrieval 版本映射：50 题均有候选 document/chunk ID，但 version ID 仍需结合完整 immutable manifest 逐题复核；R1-RET-034、R1-RET-037 的多文档规则及 R1-RET-024、R1-RET-042 的共享 Chunk 需人工确认。
4. 当前正式 AI 失败：正式报告仅保留 80/100、critical 16/30、grounding 93% 等聚合值；其引用的逐题报告不在工作树或可达 Git 对象中，20 个正式失败题 ID 不能可靠恢复，保持 `EVIDENCE_MISSING_PENDING_REVIEW`。
5. 历史逐题归类：已对可用证据中的 60 个 v2.7 失败、6 个 v2.8 失败及 5 个 v2.9 失败观察进行 retrieval、rerank、citation、claim、tool_routing、refusal、eval_fixture 分类；这些历史题不能替代当前正式 20 题证据。
6. 当前正式未通过项：AI 通过数、AI critical、grounding、未授权拦截率未测量，以及 150 题人工审批和 90 题 AI 精确证据映射。未经人工确认与真实候选环境复验，不得声明正式黄金集 PASS。
