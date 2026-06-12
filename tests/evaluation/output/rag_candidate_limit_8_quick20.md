# rag_candidate_limit_8_quick20

- 生成时间：2026-06-07 20:58:18
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：20
- 总通过率：16/20 (80.00%)
- RAG 期望命中率：100.00%
- Top-K 标题命中率：90.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：31377.8 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| price_forecast | 20 | 80.00% | 100.00% | 90.00% | 100.00% | 90.00% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：20 条

## 失败案例（4）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| price_001 | price_forecast | 明天电价风险大吗？ | default_status_ok, answer_point_hit | 5 | high_price_risk_strategy; price_forecast_logic; AI-项目进展与分析 (11) |
| price_002 | price_forecast | 明天哪些小时价格可能偏高？ | top_k_title_hit | 5 | AI-项目进展与分析 (1); pjm_day_ahead_market; day_ahead_vs_real_time |
| price_012 | price_forecast | 实时市场变化会怎样影响日前预测判断？ | top_k_title_hit | 5 | 日前市场与实时市场说明; AI-项目进展与分析 (9); 河北南部电网电力现货市场实施细则.pdf-W020260122360751867980.pdf |
| price_018 | price_forecast | 如果预测数据不足，AI 助手应该如何说明？ | answer_point_hit | 5 | system_overview; model_pipeline_explanation; AI-项目进展与分析 (11) |
