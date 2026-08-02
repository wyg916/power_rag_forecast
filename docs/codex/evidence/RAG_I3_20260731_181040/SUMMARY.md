# RAG-I3 父子 Chunk、Citation 与质量门禁证据

## 实现范围

- 分支：`codex/rag-enterprise-ingestion`。
- 从 `ParsedDocument` 确定性生成标题路径、父级原文和子 Chunk。
- 稳定生成 `document_id/version_id/parent_id/chunk_id`，父级保存内容哈希，子级保存显式 token 数。
- Citation 保存 source/version/parent/block、页码、章节路径、字符偏移、bbox、资产关联、quote 与 quote hash。
- 表格按确定性 Markdown 保存在父级，子级 locator 连续覆盖全部父级内容；表格自身 page/bbox 优先保留。
- XLSX Sheet/无版面定位逻辑表只形成 table parent/chunk，不冒充冻结资产；仅具备 page+bbox 的版面表格形成 table asset。
- 普通资产只绑定同页唯一最近顺序的 block；显式版面表格优先，关联不唯一时不绑定但仍保留资产目录。
- token counter 必须显式注入；缺失、异常、非正整数或预算不足均 fail-closed。
- 内部 DTO 明确使用 `rag-chunk-build/v1`，不会冒充冻结的 Candidate Manifest。
- `export_frozen_records` 只导出 M1 JSON Schema 的 chunk/citation/asset 字段；测试逐条使用冻结 `$defs` 校验，无法无损映射多个 citation asset 时 fail-closed。
- 质量门禁拒绝空内容、重复 ID、父级缺失、越界/缺口 locator、quote/hash/location/asset 错配、任何非 ready 资产，以及缺 hash/page/bbox 的 ready 资产。

## 测试

- I3 Chunk/Citation/质量门禁（含冻结 Schema 导出、跨页和坏例）：`9 passed in 0.38s`。
- RAG-I1 回归：`7 passed in 0.77s`。
- RAG-I2 DOCX/XLSX 回归（502 行 XLSX 已串联 build/export）：`4 passed in 1.57s`。
- RAG-I2 HTML/PDF 回归：`4 passed in 0.96s`。
- 所有测试仅使用内存 DTO 或 pytest 临时 fixture，单条命令均低于 60 秒。

## 影响、回滚与限制

- 83 份权威原件处理、`.runtime` 写入、PostgreSQL、Qdrant、网络、下载、模型加载和发布：0。
- 未修改旧处理器、配置、API、迁移或前端；仅向内部 `ParsedAsset` 追加向后兼容的可选 `content_hash` 字段。
- 回滚：集成前放弃本提交，或集成后对本包提交执行普通 `git revert`。
- 测试 token counter 为显式 fake；正式 Candidate 仍必须由后续集成注入已准入的 BGE tokenizer。
- 本包不创建正式 Candidate Release、不执行 Embedding，也不补齐 OCR_REQUIRED 资产。
