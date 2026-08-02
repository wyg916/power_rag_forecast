# RAG-RT3 实施证据摘要

## 范围与检查点

- 分支：`codex/rag-enterprise-runtime`
- 基线：`fbec4529c28741fe96f1840d95a1385f1a320b69`
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_180401_RAG_RT3_PRE`
- 本包仅修改运行时 Citation/Claim/内容安全服务、AI 企业 fallback 门禁、fake 测试和本证据。

## 实施结果

- Citation 正式出口强制具备并校验 version、page、section path、字符偏移、bbox、asset、quote 和 SHA-256。
- locator 偏移优先基于父内容或显式 citation base；quote 必须精确等于该切片。
- Chunk hash 独立复核完整 Chunk；Citation hash 独立复核 quote，禁止混用两个 SHA-256 字段。
- 未分章节资料允许空 section path；非空 bbox 必须同时具有有效页码。
- 任一候选 Citation 不完整或被篡改，整个企业检索结果立即 unavailable，不返回部分正式证据。
- Claim 必须以稳定 citation ID 绑定已验证证据；缺引用、伪造引用或无效证据目录均返回 grounding unavailable/refused。
- 纯函数内容安全识别系统覆盖、忽略前文、角色劫持、密钥、路径和工具执行诱导。
- 高风险候选隔离，中风险候选降权；所有可用文档均包装为 `untrusted_evidence`。
- 企业 AI 知识入口在 RAG 不可用或异常时直接返回空结果，不读取本地 Markdown。
- 企业检索仍只走 RT2 注入式 Qdrant store、BGE Embedding/reranker 门禁；未引入 Hash、heuristic、NPZ 或 PostgreSQL 扫描旁路。

## 测试

- Citation/Claim/内容安全及企业出口定向测试：`32 passed in 0.33s`。
- RT1、RT2、RT3 契约与运行时回归：`69 passed in 0.65s`。
- AI context pack 与聊天兼容回归：`8 passed in 1.83s`。
- 测试仅使用纯函数、fake transport 和 fake provider/reranker。
- 临时目录位于工作树 `.codex_tmp`，未向 C 盘写入测试产物。

## 外部影响与回滚

- 未连接 PostgreSQL、Qdrant、网络或真实模型；未安装依赖、下载模型、执行迁移或处理正式资料。
- 未修改 API、数据库、Compose、公共配置、权限矩阵、前端或 ingestion parser。
- 提交后使用 `git revert <RAG-RT3-commit>` 回滚；本包没有外部数据状态需要恢复。
