# RAG-R1 正式验收资产预检

## 结论

`NOT PASS`，发布门禁阻断。该结论表示正式评测输入不足，不能计算 OCR、检索和 AI 硬指标；不把“未评测”伪装为 0 分或 PASS。

## 已验证事实

- Candidate/Collection 不可变输入一致：Candidate SHA-256 `ed5f62ad50a36207ca7d0e729ae2bfb054e276b40816d8ac1da04eb376468ed7`。
- 83/83 均有终态：45 个 Candidate 发布项、24 个隔离项、14 个重复项、0 个损坏项。
- 45 documents、8,339 chunks 与 Qdrant Candidate Collection 的 8,339 points 一致。
- 本地双模型目录存在；Qdrant 1.18.2 Candidate 容器在线。当前 Python 环境没有 Paddle/PaddleOCR，也没有其他本地 OCR runtime。

## 阻断项

1. `tests/evaluation/rag_r1_ocr_gold.json` 不存在：缺少至少 30 页经人工审核的 reference text、元素 bbox 和表格单元格标注，CER、表格 F1、定位率和虚构数字无法计算。
2. `tests/evaluation/rag_r1_retrieval_gold.json` 不存在：缺少精确 50 条、绑定 `RAG-R1/document_id/version_id/chunk_id` 的独立检索黄金集。
3. `tests/evaluation/rag_r1_ai_gold.json` 不存在：缺少精确 100 题、30 条 critical、事实/数字/引用/拒答预期均独立标注的 RAG-R1 AI 集。

旧 Phase 5 资产不能替代：旧 AI 集按标题命中，旧 A3 只有 30 题且引用旧 document_id，`rag_expected_hits.json` 只是标题提示；旧检索脚本从旧库 chunk 自建 32 条 query，并采用 Recall@3 80%、Recall@5 90%、MRR 75% 的旧阈值。

## 实现与测试

- `knowledge_pipeline/enterprise/acceptance_preflight.py`：三类正式资产的数量、唯一性、人工审核声明、release/chunk 身份和 critical 约束。
- `scripts/rag_r1_acceptance_preflight.py`：真实 Candidate/Collection 输入预检并生成机器报告。
- 专项 `4 passed`；`py_compile`、`git diff --check` 均通过。
- 机器结果：`acceptance_preflight.json`，`status=BLOCKED`、`publish_allowed=false`。

## 边界与回滚

本包不连接数据库，不写 Qdrant，不创建 snapshot，不切换 alias，不改变 Candidate/Published 状态。回滚见 `rollback.md`。

