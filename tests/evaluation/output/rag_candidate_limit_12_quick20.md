# rag_candidate_limit_12_quick20

- 生成时间：2026-06-07 21:16:25
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：20
- 总通过率：18/20 (90.00%)
- RAG 期望命中率：100.00%
- Top-K 标题命中率：95.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：36811.6 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| price_forecast | 20 | 90.00% | 100.00% | 95.00% | 100.00% | 95.00% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：20 条

## 失败案例（2）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| price_001 | price_forecast | 明天电价风险大吗？ | default_status_ok, answer_point_hit | 5 | high_price_risk_strategy; pjm_day_ahead_market; price_forecast_logic |
| price_002 | price_forecast | 明天哪些小时价格可能偏高？ | top_k_title_hit | 5 | AI-项目进展与分析 (1); pjm_day_ahead_market; day_ahead_vs_real_time |
