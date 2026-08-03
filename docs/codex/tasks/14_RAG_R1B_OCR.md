# RAG-R1B 并行任务：OCR/VLM 证据闭环

## 目标

在不发布、不写正式数据库的前提下，完成至少 30 页人工真值、CER、表格 F1、定位完整率和编造数字门禁。不得把自动生成标签或模型自评冒充人工真值。

## 工作线

- 分支：`beta10d/rag-r1b-ocr`
- 工作树：`E:\智能运营分析项目_worktrees\beta10d_rag_r1b_ocr`
- 精确基线 HEAD：由主控最终交接矩阵公布；开始前必须 `git rev-parse HEAD` 精确一致。

## 允许修改范围

- `knowledge_pipeline/enterprise/ocr_contracts.py`
- `knowledge_pipeline/enterprise/ocr_pipeline.py`
- `knowledge_pipeline/enterprise/parsers/pdf_parser.py`
- `knowledge_pipeline/enterprise/quality.py`
- `scripts/rag_r1_ocr_acceptance.py`（允许新增）
- `tests/test_rag_enterprise_ocr_pipeline.py`
- `tests/test_rag_r1_ocr_acceptance.py`（允许新增）
- `tests/evaluation/rag_r1_ocr_gold_30.json`（允许新增；必须记录人工标注来源和核验状态）
- `docs/codex/evidence/RAG_R1B_OCR_*`（仅本任务证据）

## 禁止范围

- 不得修改 PostgreSQL、迁移、公共配置、Compose、公共 API、release 状态、Qdrant alias/snapshot。
- 不得修改黄金集任务和检索性能任务的文件。
- 不得 merge、cherry-pick、rebase、push 发布分支或直接合入主控。
- 不得下载、加载或调用未获主控授权的 OCR/VLM 模型；不得写源文件目录。

## 交付门禁

- 人工真值页数不少于 30，原页哈希、标注人/复核人、时间和来源可审计。
- CER `<=5%`、表格 F1 `>=0.90`、定位完整率 `100%`、编造数字 `0`。
- 重跑幂等，失败保持 fail-closed；证据不含密码、token、完整连接串。
- 只提交本任务允许文件，并向主控报告提交 SHA；不得自行合并。

