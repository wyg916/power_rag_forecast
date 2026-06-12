# v2_9_quality_sample_report

- 生成时间：2026-06-08 14:24:37
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：30
- 总通过率：29/30 (96.67%)
- RAG 期望命中率：100.00%
- Top-K 标题命中率：100.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：44043.4 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| daily_chat | 2 | 100.00% | 0.00% | 100.00% | 100.00% | 100.00% |
| load_weather | 5 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| model_explain | 5 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| price_forecast | 5 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| spike_risk | 5 | 80.00% | 100.00% | 100.00% | 100.00% | 80.00% |
| system_usage | 3 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| trading_strategy | 5 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：28 条
- embedding=- / model=- / reranker=-：2 条

## 失败案例（1）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| spike_001 | spike_risk | 尖峰概率高是不是一定代表价格会暴涨？ | answer_point_hit | 5 | peak_spike_risk_explanation; ai_assistant_explanation_policies; risk_level_rules |
