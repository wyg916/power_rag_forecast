# bge_embedding_reranker_report

- 生成时间：2026-06-06 14:14:48
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：100
- 总通过率：64/100 (64.00%)
- RAG 期望命中率：68.89%
- Top-K 标题命中率：72.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：25235.8 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| daily_chat | 10 | 40.00% | 0.00% | 100.00% | 100.00% | 40.00% |
| load_weather | 15 | 86.67% | 93.33% | 93.33% | 100.00% | 93.33% |
| model_explain | 15 | 60.00% | 60.00% | 60.00% | 100.00% | 80.00% |
| price_forecast | 20 | 65.00% | 65.00% | 65.00% | 100.00% | 75.00% |
| spike_risk | 15 | 73.33% | 80.00% | 80.00% | 100.00% | 80.00% |
| system_usage | 10 | 40.00% | 40.00% | 40.00% | 100.00% | 60.00% |
| trading_strategy | 15 | 66.67% | 66.67% | 66.67% | 100.00% | 66.67% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：63 条
- embedding=- / model=- / reranker=-：37 条

## 失败案例（36）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| price_002 | price_forecast | 明天哪些小时价格可能偏高？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_005 | price_forecast | 如果模型预测晚高峰价格高，我应该先看什么指标？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| price_006 | price_forecast | 预测区间变宽说明什么？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_007 | price_forecast | 为什么有些小时预测价格接近零？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_009 | price_forecast | 明天电价均价高不高？ | rag_expectation_ok, top_k_title_hit | 0 |  |
| price_016 | price_forecast | 低价窗口是否一定适合采购？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_018 | price_forecast | 如果预测数据不足，AI 助手应该如何说明？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| weather_011 | load_weather | 温度升高时应该关注哪些预测字段？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| weather_012 | load_weather | 天气数据不新鲜会影响 AI 助手判断吗？ | answer_point_hit | 5 | model_retrain_rules; model_pipeline_explanation; system_overview |
| spike_001 | spike_risk | 尖峰概率高是不是一定代表价格会暴涨？ | answer_point_hit | 5 | peak_spike_risk_explanation; risk_level_rules; 风险等级定义 |
| spike_003 | spike_risk | 为什么晚高峰容易出现尖峰价格？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| spike_009 | spike_risk | 尖峰价格预测偏差为什么经常更大？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| spike_010 | spike_risk | 如何判断一个高价小时是不是异常价格？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| model_005 | model_explain | 真实值回填不足时能判断模型好坏吗？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, answer_point_hit | 0 |  |
| model_006 | model_explain | 模型漂移可能由哪些因素造成？ | rag_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| model_008 | model_explain | 模型版本变化会影响预测口径吗？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| model_009 | model_explain | 数据质量问题会怎样影响模型预测？ | rag_expectation_ok, top_k_title_hit | 0 |  |
| model_010 | model_explain | 模型训练流程大概包括哪些步骤？ | rag_expectation_ok, top_k_title_hit | 0 |  |
| model_015 | model_explain | 为什么模型不应该自动决定生产切换？ | rag_expectation_ok, top_k_title_hit, answer_point_hit | 0 |  |
| strategy_003 | trading_strategy | 低价窗口应该如何利用？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| strategy_005 | trading_strategy | 异常价格出现时应该先做什么？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| strategy_009 | trading_strategy | 负价是不是一定可以买入？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| strategy_010 | trading_strategy | 高价预测和储能套利之间有什么关系？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, answer_point_hit | 0 |  |
| strategy_013 | trading_strategy | 如果连续低价时段出现，采购策略要注意什么？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| system_003 | system_usage | AI 助手能帮我分析什么？ | rag_expectation_ok, top_k_title_hit, answer_point_hit | 0 |  |
| system_004 | system_usage | 开发者模式能看到什么？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| system_005 | system_usage | 为什么普通模式不显示工具调用？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| system_006 | system_usage | 预测中心和策略中心分别看什么？ | rag_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| system_008 | system_usage | 如果没有预测数据，系统应该怎么提示？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| system_009 | system_usage | 模型运维页面主要关注什么？ | rag_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| daily_002 | daily_chat | 你是谁？ | answer_point_hit | 0 |  |
| daily_003 | daily_chat | 你好 | answer_point_hit | 0 |  |
| daily_004 | daily_chat | 谢谢你 | answer_point_hit | 0 |  |
| daily_006 | daily_chat | 早上好 | answer_point_hit | 0 |  |
| daily_007 | daily_chat | 现在几点？ | tool_expectation_ok, answer_point_hit | 0 |  |
| daily_009 | daily_chat | 请用一句话回答 | answer_point_hit | 0 |  |
