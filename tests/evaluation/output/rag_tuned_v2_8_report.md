# rag_tuned_v2_8_report

- 生成时间：2026-06-08 13:06:49
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：100
- 总通过率：94/100 (94.00%)
- RAG 期望命中率：100.00%
- Top-K 标题命中率：98.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：38370.3 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| daily_chat | 10 | 100.00% | 0.00% | 100.00% | 100.00% | 100.00% |
| load_weather | 15 | 86.67% | 100.00% | 100.00% | 100.00% | 86.67% |
| model_explain | 15 | 93.33% | 100.00% | 100.00% | 100.00% | 93.33% |
| price_forecast | 20 | 95.00% | 100.00% | 95.00% | 100.00% | 100.00% |
| spike_risk | 15 | 93.33% | 100.00% | 100.00% | 100.00% | 93.33% |
| system_usage | 10 | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| trading_strategy | 15 | 93.33% | 100.00% | 93.33% | 100.00% | 100.00% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：91 条
- embedding=- / model=- / reranker=-：9 条

## 失败案例（6）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| price_010 | price_forecast | 最高价和平均价哪个更适合判断风险？ | top_k_title_hit | 5 | ai_assistant_explanation_policies; high_price_risk_strategy; 风险等级定义 |
| weather_007 | load_weather | 天气预报误差会不会放大电价预测误差？ | answer_point_hit | 5 | forecast_error_explanation; price_forecast_logic; high_price_risk_strategy |
| weather_012 | load_weather | 天气数据不新鲜会影响 AI 助手判断吗？ | answer_point_hit | 5 | ai_assistant_explanation_policies; ai_assistant_explanation_policies; model_retrain_rules |
| spike_001 | spike_risk | 尖峰概率高是不是一定代表价格会暴涨？ | answer_point_hit | 5 | peak_spike_risk_explanation; ai_assistant_explanation_policies; risk_level_rules |
| model_007 | model_explain | 高价时段误差大该不该马上切换模型？ | answer_point_hit | 5 | high_price_risk_strategy; model_retrain_rules; forecast_error_explanation |
| strategy_006 | trading_strategy | 储能放电策略要结合哪些限制？ | top_k_title_hit | 5 | 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》; 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》; 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》 |
