# rag_tuned_after_import_report

- 生成时间：2026-06-08 00:28:51
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：100
- 总通过率：93/100 (93.00%)
- RAG 期望命中率：100.00%
- Top-K 标题命中率：99.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：41722.3 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| daily_chat | 10 | 100.00% | 0.00% | 100.00% | 100.00% | 100.00% |
| load_weather | 15 | 86.67% | 100.00% | 100.00% | 100.00% | 86.67% |
| model_explain | 15 | 93.33% | 100.00% | 100.00% | 100.00% | 93.33% |
| price_forecast | 20 | 95.00% | 100.00% | 100.00% | 100.00% | 95.00% |
| spike_risk | 15 | 93.33% | 100.00% | 100.00% | 100.00% | 93.33% |
| system_usage | 10 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| trading_strategy | 15 | 86.67% | 100.00% | 93.33% | 100.00% | 93.33% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：91 条
- embedding=- / model=- / reranker=-：9 条

## 失败案例（7）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| price_018 | price_forecast | 如果预测数据不足，AI 助手应该如何说明？ | answer_point_hit | 5 | system_overview; ai_assistant_answer_rules; model_pipeline_explanation |
| weather_012 | load_weather | 天气数据不新鲜会影响 AI 助手判断吗？ | answer_point_hit | 5 | model_retrain_rules; model_pipeline_explanation; system_overview |
| weather_015 | load_weather | 天气和负荷哪个对明天价格更重要？ | answer_point_hit | 5 | load_weather_price_relationship; day_ahead_vs_real_time; 负荷与电价关系 |
| spike_001 | spike_risk | 尖峰概率高是不是一定代表价格会暴涨？ | answer_point_hit | 5 | peak_spike_risk_explanation; risk_level_rules; AI-项目进展与分析 (1) |
| model_014 | model_explain | 模型误差和业务风险有什么关系？ | answer_point_hit | 5 | forecast_error_explanation; high_price_risk_strategy; model_pipeline_explanation |
| strategy_004 | trading_strategy | 峰谷价差大是不是一定有套利机会？ | answer_point_hit | 5 | peak_valley_spread_strategy; prediction_interval_explanation; AI-项目进展与分析 (6) |
| strategy_006 | trading_strategy | 储能放电策略要结合哪些限制？ | top_k_title_hit | 5 | 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》; 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》; 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》 |
