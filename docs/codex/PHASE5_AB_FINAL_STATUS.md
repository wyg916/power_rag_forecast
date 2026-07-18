# PHASE5-A/B 最终状态

- 最终结论：`PASS`
- 分支：`p5-frontend-ai-experience`
- HEAD：`251378fcf1b0fe83a058b12c7c647f126b454443`
- 隔离数据库：`intelligent_ops_phase5_ab_test`
- Schema：Alembic `0014_t003_run_transaction`
- 总证据：`E:\智能运营分析项目_备份\phase5\20260718_195145245_PHASE5_AB_FINAL_RESULT`

## 子阶段门禁

| 子阶段 | 结论 | 关键结果 |
|---|---|---|
| PHASE5-A1 | PASS | Document、Chunk、混合检索、过滤、Citation、无证据拒答契约通过 |
| PHASE5-A2.1 | PASS | 隔离知识库导入、Chunk 落库、幂等、版本治理、失败回滚与读无副作用通过 |
| PHASE5-A2.2 | PASS | BGE 1024 维 Embedding、持久化精确余弦索引、混合检索与过滤通过 |
| PHASE5-A3.1 | PASS | 指定两道失败题复验均 PASS；RAG 30 题最终 29/30，critical 30/30 |
| PHASE5-A | PASS | A1、A2.1、A2.2、A3 门禁全部恢复 |
| PHASE5-B | PASS | 最终单次完整 100 题 95/100，全部分类与安全门禁达标 |

## 最终指标

- 有效检索文档/Chunk：40/244；有效 Chunk 总 token 142,519，平均 584.09，中位数 657，范围 47–1,040；active 文档重复内容哈希组 0。
- Embedding：`sentence_transformers` / `bge-large-zh-v1.5` / 1024 / `bge-large-zh-v1.5-v1`；244 条有效向量，fallback、NaN、Inf 为 0。
- 检索：Recall@3 81.25%、Recall@5 96.88%、MRR 75.62%、Citation 命中 96.88%、Citation 完整性 100%、过滤与无答案拒答 100%。
- RAG 30 题：29/30；全部 critical PASS；Citation 完整性与 unavailable 拒答均 100%。
- AI 100 题：95/100；critical 30/30；Citation 完整性 100%、grounding 97%、hallucination 0%、unavailable/refusal 100%、route/domain/source 99%/98%/99%、tool success 100%、tool mismatch 0。

## 安全边界与回归

- 100 题执行前后 17 张观测表行数均无变化；读取无 seed、激活、同步或预测副作用。
- 使用一个冻结 historical 预测 run（24 行），未执行正式预测、未创建生产 Active、未生成报告或策略。
- A1/A2/RAG 39 passed；T004/T001/T002 与 Phase4 59 passed；T003 19 passed；T005 3 passed；Phase4 runtime 16 passed；前端 TypeScript 与 Vite build PASS。
- FastAPI `/api/health` 与 PostgreSQL `/api/db/health` 均返回 `ok=true`；浏览器核心链路无控制台错误；隔离 Redis/Celery 健康任务成功并已停止，Redis 持久卷保留。
- Artifact 当前校验 11/11，mismatch 0。

## 未解决但不阻断的问题

- RAG 非 critical 题 `P5A-MODEL-03` 仍未通过。
- AI 100 题有 5 道非 critical 失败：`P5B-018`、`P5B-034`、`P5B-042`、`P5B-075`、`P5B-077`。
- 旧 `run_health_check.bat` 仍探测 MySQL/Ollama，与当前 PostgreSQL/FastAPI 事实不一致；本次使用真实 API 健康端点验收。
- 当前虚拟环境缺少 FastAPI 0.139 / Starlette 1.3.1 测试客户端所需的 `httpx2`；本次仅安装到 E 盘隔离证据目录，尚未写入依赖清单。

## 阶段边界

PHASE5-A 与 PHASE5-B 已完成。PHASE5-C、报告生成、策略生成、交易执行、生产部署、预测模型训练或改造均未开始，也不在本次授权范围内。
