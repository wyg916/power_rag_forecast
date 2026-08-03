# RAG-R1B AI-only 开发/预发布验收口径修订

## 1. 状态与授权

- 生效时间：2026-08-04。
- 适用分支：`beta10d/rag-r1b-evidence-closure`。
- 生效前主控 HEAD：`bcfff43425efc5028a3e7ac60d6a52a74be4e44e`。
- 用户明确取消本里程碑等待真人标注员或真人复核员的要求，授权以独立 AI 多角色共识替代 OCR、Retrieval 50 和 AI 100/critical 30 的参与者身份门槛。
- 本修订只适用于开发/预发布技术验收，不等同于真人金标生产验收，不授权正式生产切换。

验收模式名称：

- `AI-SURROGATE GOLD STANDARD`
- `AI INDEPENDENT CONSENSUS REVIEW`

## 2. 强制身份与状态字段

所有自动共识数据必须保留以下字段和值：

```text
human_verified=false
automated_consensus_verified=true
verification_mode=multi_agent_independent_consensus
production_human_signoff=false
```

不得伪造真人姓名、真人标注身份、真人复核身份或将 AI 自动结果回写为人工金标。AI 来源、角色、复核次数、输入隔离方式、分歧及裁决必须可审计。

## 3. 独立复核角色

### OCR 30 页

- `annotator_origin=codex_ai_ocr_extractor`
- `reviewer_origin=codex_ai_independent_visual_reviewer`
- `adjudicator_origin=codex_ai_consensus_adjudicator`
- Extractor 与 Reviewer 必须在独立上下文中只看页面图像，各自生成结果；Adjudicator 只比较图像、A、B 和结构化差异。

### Retrieval 50

- `designer_origin=codex_ai`
- `evidence_mapper_origin=codex_ai_independent`
- `judge_origin=codex_ai_independent`
- Question Designer 不读取系统检索结果；Evidence Mapper 独立映射 immutable document/version/chunk/page/section；Judge 检查证据真实性、答案泄漏、系统定制和 critical 合理性。

### AI 100 / critical 30

- Evaluation Designer、Evidence and Behavior Mapper、Independent Evaluation Judge 使用相互隔离的输入和审核记录。
- 每题必须覆盖 expected route/tool/claims/citations/refusal、forbidden claims、numeric tolerance、unit 和 scoring rubric。

## 4. 数据冻结与隐藏集

- Retrieval 50 冻结为开发集 40 题和隐藏验收集 10 题。
- AI 100 冻结为开发整改集 70 题和隐藏验收集 30 题；至少 10 道 critical 进入隐藏验收集。
- 检索、rerank、性能和生产实现不得读取隐藏验收集答案或评分标准。
- 冻结后不得根据系统失败结果修改标准答案、删除失败题、降低 critical 或把系统当前输出作为标准答案。

## 5. OCR 代理指标命名

没有真人真值时，只允许报告：

- `consensus_CER_proxy`
- `consensus_table_F1_proxy`

报告必须同时声明 `AI consensus proxy` 与 `human gold unavailable`，不得把代理值描述为真人金标 CER/F1。

## 6. 不变的技术门槛

本修订只替代“参与者必须是真人”这一项，不降低任何技术门槛：

- OCR：30/30 完成；未裁决文字、表格单元格、页码、数字和 bbox 冲突均为 0；虚构数字 0。
- Retrieval：R@3 `>=90%`、R@5 `>=98%`、MRR `>=85%`、critical `100%`、Citation integrity `100%`。
- AI：总体 `>=97/100`、critical `30/30`、grounding `>=98%`、Citation integrity `100%`、幻觉数字 0、无证据拒答率 `100%`、未授权拦截率 `100%`。
- 性能：含正式 reranker、ACL、Citation 和 50 题的端到端 P95 `<=1.5s`，同时报告 cold/warm 与 hit/miss。
- 安全、真实性、迁移、幂等、回滚、RTO/RPO 和数据库/Qdrant 非预期变化门禁保持不变。

不得以关闭 reranker、跳过 ACL/Citation、缩小题集、只测缓存命中、Fake Qdrant、Hash Embedding、heuristic rerank 或本地 fallback 制造 PASS。

## 7. 结论口径

只有全部开发/预发布技术门槛真实通过时，才允许输出：

```text
RAG-R1 DEVELOPMENT ACCEPTANCE PASS
RAG-R1 PRODUCTION HUMAN-GOLD GATE WAIVED FOR THIS MILESTONE
PRODUCTION CUTOVER NO
```

若 AI 质量、检索 P95 或任一技术门槛未通过，必须输出 `RAG-R1 NOT PASS`；不得用本修订覆盖失败事实。

## 8. 发布与生产边界

- RAG-R1 当前继续保持 Candidate、`is_current=false`。
- 开发验收全部通过前，不创建 PostgreSQL/Qdrant snapshot，不切换 alias，不更新 current release。
- 全部通过后，只授权在本地开发/预发布环境执行 snapshot、Candidate validate、alias 映射保存、切换、smoke、回滚及 RTO/RPO 演练。
- 正式生产发布、生产 alias 切换、生产 release 激活、Day 9/Day 10 和生产切换仍为 NO。
- 不删除旧 Collection、旧 release、历史 NOT PASS 报告或失败证据。

## 9. 生产准入保留条件

本里程碑的 AI 自动共识不构成生产真人金标准入。后续生产准入仍需真人抽样，除非用户另行、明确、单独豁免；任何后续豁免不得追溯性地把本轮数据标记为真人核验。
