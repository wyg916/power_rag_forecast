# RAG-I5 Candidate Corpus 编排与确定性清单证据

## 基线与范围

- 基线提交：`e46964028d199d2ba2baf3784ff00f3b4ed1f432`。
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_185951_RAG_I5_PRE`。
- 仅新增 ingestion Candidate 编排器、fixture/fake 测试和本证据。

## 实现

- 以 I1 `SourceLedgerEntry` 为唯一源台账；严格验证 83 条终态、唯一 source/path、READY 内容去重及 duplicate→READY canonical 的 hash/path 关系。
- 注入 `ParsedSourceInput`、I3 Candidate builder 和 frozen exporter；支持原件 hash 与受控转换产物 hash 分离审计。
- fixture 同时覆盖直接 ParsedDocument 与真实 I4 OCR fixture→ParsedDocument 映射接缝。
- READY 原件只会进入唯一 document/version，或写入确定性隔离原因；duplicate、quarantined、corrupt 不生成版本。
- I3 parent/child quality 与 frozen records 逐字段复核，覆盖版本、内容 hash、quote/hash、locator、资产、空 Chunk 和全局 ID 冲突。
- 外层 `rag-candidate-orchestration/v1` 保存 ledger SHA/status、profile、version source/content hash、计数、重复、隔离及 artifact SHA-256。
- 内层保持冻结 `rag-candidate-corpus/v1`，并通过 M1 JSON Schema 校验；`corpus_sha256` 与外层 `artifact_sha256` 均可复算。
- 相同输入、逆序 ledger 和逆序 parsed mapping 构建结果字节完全一致。

## 测试

- RAG-I5 synthetic 83-row in-memory fixture：`11 passed in 0.64s`。
- RAG-I1 回归：`7 passed in 1.15s`；RAG-I3 回归：`9 passed in 0.90s`；RAG-I4 OCR 回归：`3 passed in 1.28s`。
- 测试不读取或处理 83 份正式原件；只使用内存台账和 ParsedDocument fixture。

## 影响与回滚

- `.runtime`、PostgreSQL、Qdrant、网络、外部模型/转换工具、正式原件和正式发布影响均为 0。
- 集成前放弃本提交；集成后使用普通 `git revert` 回滚。
