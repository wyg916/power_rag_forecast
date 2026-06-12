# smoke_bge_reranker_after_reindex

- 生成时间：2026-06-06 12:59:04
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：1
- 总通过率：0/1 (0.00%)
- RAG 期望命中率：100.00%
- Top-K 标题命中率：0.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：17497.5 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| price_forecast | 1 | 0.00% | 100.00% | 0.00% | 100.00% | 100.00% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：1 条

## 失败案例（1）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| price_001 | price_forecast | 明天电价风险大吗？ | top_k_title_hit | 5 | policy_6; pjm_dom_node_background; risk_level_rules |
