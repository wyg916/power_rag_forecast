# rag_tuned_quick20_candidate20

- 生成时间：2026-06-07 19:12:59
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：20
- 总通过率：6/20 (30.00%)
- RAG 期望命中率：85.00%
- Top-K 标题命中率：40.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：48524.5 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| price_forecast | 20 | 30.00% | 85.00% | 40.00% | 100.00% | 75.00% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：17 条
- embedding=- / model=- / reranker=-：3 条

## 失败案例（14）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| price_002 | price_forecast | 明天哪些小时价格可能偏高？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_005 | price_forecast | 如果模型预测晚高峰价格高，我应该先看什么指标？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| price_006 | price_forecast | 预测区间变宽说明什么？ | answer_point_hit | 5 | prediction_interval_explanation; AI-项目进展与分析 (1); 预测模型字段说明 |
| price_007 | price_forecast | 为什么有些小时预测价格接近零？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_008 | price_forecast | 电价预测主要依赖哪些数据？ | top_k_title_hit | 5 | AI-项目进展与分析 (1); AI-项目进展与分析; AI-项目进展与分析 (10) |
| price_009 | price_forecast | 明天电价均价高不高？ | top_k_title_hit | 5 | AI-项目进展与分析 (1); AI-项目进展与分析; AI-项目进展与分析 (11) |
| price_010 | price_forecast | 最高价和平均价哪个更适合判断风险？ | top_k_title_hit | 5 | high_price_risk_strategy; peak_valley_spread_strategy; AI-项目进展与分析 |
| price_012 | price_forecast | 实时市场变化会怎样影响日前预测判断？ | top_k_title_hit | 5 | AI-项目进展与分析 (9); 河北南部电网电力现货市场实施细则.pdf-W020260122360751867980.pdf; 河北南部电网电力现货市场实施细则.pdf-W020260122360751867980.pdf |
| price_014 | price_forecast | LMP 节点价格为什么会和区域均价不同？ | top_k_title_hit | 5 | 绿证交易用户手册2026.06; 绿证交易用户手册2026.06; 绿证交易用户手册2026.06 |
| price_015 | price_forecast | 电价突然跳高时先判断模型问题还是市场问题？ | top_k_title_hit | 5 | AI-项目进展与分析 (4); AI-项目进展与分析 (1); AI-项目进展与分析 (10) |
| price_016 | price_forecast | 低价窗口是否一定适合采购？ | answer_point_hit | 5 | low_price_opportunity_strategy; 售电公司交易规则; peak_valley_spread_strategy |
| price_017 | price_forecast | 电价预测结果里的风险等级应该怎么用？ | top_k_title_hit | 5 | AI-项目进展与分析 (1); AI-项目进展与分析 (10); AI-项目进展与分析 (9) |
| price_018 | price_forecast | 如果预测数据不足，AI 助手应该如何说明？ | top_k_title_hit, answer_point_hit | 5 | AI-项目进展与分析 (11); 预测结果字段说明; AI-项目进展与分析 (1) |
| price_019 | price_forecast | 价格预测可信度要结合哪些因素判断？ | top_k_title_hit | 5 | AI-项目进展与分析 (1); AI-项目进展与分析 (9); AI-项目进展与分析 (10) |
