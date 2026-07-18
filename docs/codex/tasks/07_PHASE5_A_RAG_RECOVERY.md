# PHASE5-A：RAG_RECOVERY

## 目标

在隔离知识库 `intelligent_ops_phase5_rag_test` 中恢复显式文档导入、版本化 chunk、BGE Embedding、混合检索、真实 citation 和单轮 AI RAG 回答闭环。

## 允许范围

- 知识库 Repository、Service、API、AI RAG 工具与最小回答契约。
- `knowledge_pipeline` 显式导入程序。
- PHASE5-A 专项测试、30 题基线和证据。

## 禁止范围

- 真实业务数据库、预测模型、生产 Active、正式预测。
- 自动 seed、读取触发持久 Embedding、静默 Provider fallback。
- 报告、策略、AI 100 题、多 Agent 和大规模 UI。
- 自动 Git add、commit、push。

## 验收要点

- 200–300 个有效 chunk，稳定 document/chunk 身份，重复内容治理。
- Embedding 仅显式生成，Provider 或维度错误 fail-closed。
- active、domain、source_type 和 score threshold 过滤。
- citation 的 document_id、chunk_id、quote 可从数据库回读验证。
- 无证据返回 `unavailable`。
- 30 题基线、六类读取各 100 次无知识库副作用、故障测试通过。
- T004、T001、T002、T003、T005、Phase4 runtime 及运行栈不退化。
