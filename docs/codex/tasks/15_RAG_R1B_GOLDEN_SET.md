# RAG-R1B 并行任务：黄金集治理

## 目标

完成人工核验的 Retrieval 50 题和 AI 100 题黄金集治理，补齐 provenance、critical 标识、期望证据/答案点和双人复核状态；本任务只治理评测输入与评测契约，不修生产业务逻辑。

## 工作线

- 分支：`beta10d/rag-r1b-golden-set`
- 工作树：`E:\智能运营分析项目_worktrees\beta10d_rag_r1b_golden_set`
- 精确基线 HEAD：由主控最终交接矩阵公布；开始前必须 `git rev-parse HEAD` 精确一致。

## 允许修改范围

- `tests/evaluation/rag_r1_retrieval_golden_50.json`
- `tests/evaluation/ai_assistant_eval_questions.json`
- `tests/evaluation/phase5_base_30_questions.json`
- `tests/evaluation/day8_golden_questions.json`
- `tests/evaluation/rag_r1_golden_manifest.json`（允许新增）
- `scripts/rag_r1_candidate_ai_acceptance.py`
- `tests/test_rag_r1_candidate_ai_acceptance.py`（允许新增）
- `docs/codex/evidence/RAG_R1B_GOLDEN_*`（仅本任务证据）

## 禁止范围

- 不得修改生产后端、前端、OCR、检索/reranker 实现、PostgreSQL、迁移、公共配置、Compose。
- 不得创建 snapshot、切换 alias、修改 release 状态、发布或生产切换。
- 不得用模型生成答案后自称人工标注；现有 `human_verified=false` 只能由真实人工复核事实改变。
- 不得 merge、cherry-pick、rebase 或直接合入主控。

## 交付门禁

- Retrieval 50 与 AI 100 数量、唯一 ID、critical 30/30、领域分布和引用期望可复核。
- 每题记录 label provenance、人工标注/复核状态；无法确认的题保持未核验，不得凑数。
- 评测器对缺失、重复、未核验、无证据或 schema 漂移 fail-closed。
- 只提交本任务允许文件，并向主控报告提交 SHA；不得自行合并。

