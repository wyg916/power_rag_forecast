# after_knowledge_import_restart_report

- 生成时间：2026-06-07 17:12:02
- Base URL：`http://127.0.0.1:8001`
- 模型路由：`auto`
- 题目总数：100
- 总通过率：40/100 (40.00%)
- RAG 期望命中率：68.89%
- Top-K 标题命中率：54.00%
- 默认隐藏调试字段通过率：100.00%
- 平均默认响应耗时：30296.7 ms

## 分类结果

| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |
|---|---:|---:|---:|---:|---:|---:|
| daily_chat | 10 | 40.00% | 0.00% | 100.00% | 100.00% | 40.00% |
| load_weather | 15 | 66.67% | 93.33% | 93.33% | 100.00% | 73.33% |
| model_explain | 15 | 40.00% | 60.00% | 46.67% | 100.00% | 73.33% |
| price_forecast | 20 | 20.00% | 65.00% | 20.00% | 100.00% | 75.00% |
| spike_risk | 15 | 66.67% | 80.00% | 80.00% | 100.00% | 73.33% |
| system_usage | 10 | 30.00% | 40.00% | 30.00% | 100.00% | 60.00% |
| trading_strategy | 15 | 20.00% | 66.67% | 26.67% | 100.00% | 60.00% |

## 检索与模型信息

- embedding=sentence_transformers / model=bge-large-zh-v1.5 / reranker=bge：63 条
- embedding=- / model=- / reranker=-：37 条

## 失败案例（60）

| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |
|---|---|---|---|---:|---|
| price_001 | price_forecast | 明天电价风险大吗？ | top_k_title_hit | 5 | AI-项目进展与分析 (11); AI-项目进展与分析; 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知 |
| price_002 | price_forecast | 明天哪些小时价格可能偏高？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_003 | price_forecast | 日前电价预测值能不能直接作为交易价格？ | top_k_title_hit | 5 | AI-项目进展与分析 (9); AI-项目进展与分析 (1); AI-项目进展与分析 |
| price_004 | price_forecast | 预测电价和真实结算电价为什么会有差异？ | top_k_title_hit | 5 | AI-项目进展与分析; AI-项目进展与分析 (1); AI-项目进展与分析 (10) |
| price_005 | price_forecast | 如果模型预测晚高峰价格高，我应该先看什么指标？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| price_006 | price_forecast | 预测区间变宽说明什么？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_007 | price_forecast | 为什么有些小时预测价格接近零？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_008 | price_forecast | 电价预测主要依赖哪些数据？ | top_k_title_hit | 5 | AI-项目进展与分析 (1); AI-项目进展与分析; AI-项目进展与分析 (5) |
| price_009 | price_forecast | 明天电价均价高不高？ | rag_expectation_ok, top_k_title_hit | 0 |  |
| price_010 | price_forecast | 最高价和平均价哪个更适合判断风险？ | top_k_title_hit | 5 | high_price_risk_strategy; 河北南部电网电力现货市场实施细则.pdf-W020260122360751867980.pdf; 河北南部电网电力市场信息披露实施细则.pdf-W020260122360751964570.pdf |
| price_012 | price_forecast | 实时市场变化会怎样影响日前预测判断？ | top_k_title_hit | 5 | AI-项目进展与分析 (9); 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知; 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知 |
| price_015 | price_forecast | 电价突然跳高时先判断模型问题还是市场问题？ | top_k_title_hit | 5 | AI-项目进展与分析; AI-项目进展与分析 (5); 河北省发展和改革委员会关于优化调整河北南网工商业及其他用户分时电价政策的通知 |
| price_016 | price_forecast | 低价窗口是否一定适合采购？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_017 | price_forecast | 电价预测结果里的风险等级应该怎么用？ | top_k_title_hit | 5 | AI-项目进展与分析; AI-项目进展与分析 (1); AI-项目进展与分析 (9) |
| price_018 | price_forecast | 如果预测数据不足，AI 助手应该如何说明？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| price_019 | price_forecast | 价格预测可信度要结合哪些因素判断？ | top_k_title_hit | 5 | AI-项目进展与分析 (1); AI-项目进展与分析 (9); 河北南部电网电力现货市场实施细则.pdf-W020260122360751867980.pdf |
| weather_005 | load_weather | 负荷和电价之间是线性关系吗？ | answer_point_hit | 5 | AI-项目进展与分析 (5); AI-项目进展与分析; AI-项目进展与分析 (6) |
| weather_007 | load_weather | 天气预报误差会不会放大电价预测误差？ | answer_point_hit | 5 | 天气与电价关系; forecast_error_explanation; price_forecast_logic |
| weather_011 | load_weather | 温度升高时应该关注哪些预测字段？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| weather_012 | load_weather | 天气数据不新鲜会影响 AI 助手判断吗？ | answer_point_hit | 5 | 负荷、天气与电价关系; 模型流程说明; 模型重训判断规则 |
| weather_013 | load_weather | 负荷高但电价没涨可能是什么原因？ | answer_point_hit | 5 | AI-项目进展与分析 (5); AI-项目进展与分析 (6); AI-项目进展与分析 |
| spike_001 | spike_risk | 尖峰概率高是不是一定代表价格会暴涨？ | answer_point_hit | 5 | peak_spike_risk_explanation; AI-项目进展与分析 (1); risk_level_rules |
| spike_003 | spike_risk | 为什么晚高峰容易出现尖峰价格？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| spike_009 | spike_risk | 尖峰价格预测偏差为什么经常更大？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| spike_010 | spike_risk | 如何判断一个高价小时是不是异常价格？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| spike_013 | spike_risk | 如果明天连续多个小时尖峰风险高，应该怎么处理？ | answer_point_hit | 5 | AI-项目进展与分析 (11); peak_valley_spread_strategy; model_retrain_rules |
| model_004 | model_explain | MAE 和 RMSE 在电价预测里怎么理解？ | top_k_title_hit | 5 | 国家发展改革委关于降低燃煤发电上网电价; 国家发展改革委关于降低燃煤发电上网电价和一般工商业用电价格的通知 (发改价格〔2015〕3105号); 电价预测逻辑说明 |
| model_005 | model_explain | 真实值回填不足时能判断模型好坏吗？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, answer_point_hit | 0 |  |
| model_006 | model_explain | 模型漂移可能由哪些因素造成？ | rag_expectation_ok, top_k_title_hit, keyword_hit | 0 |  |
| model_007 | model_explain | 高价时段误差大该不该马上切换模型？ | answer_point_hit | 5 | high_price_risk_strategy; forecast_error_explanation; peak_valley_spread_strategy |
| model_008 | model_explain | 模型版本变化会影响预测口径吗？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| model_009 | model_explain | 数据质量问题会怎样影响模型预测？ | rag_expectation_ok, top_k_title_hit | 0 |  |
| model_010 | model_explain | 模型训练流程大概包括哪些步骤？ | rag_expectation_ok, top_k_title_hit | 0 |  |
| model_013 | model_explain | 特征工程变化会导致预测结果变化吗？ | top_k_title_hit | 5 | 新型储能电站建设工程质量监督大纲-9296ad160ac140888b20dbc4d54ae917.pdf; 新型储能电站建设工程质量监督大纲-9296ad160ac140888b20dbc4d54ae917.pdf; 新型储能电站建设工程质量监督大纲-9296ad160ac140888b20dbc4d54ae917.pdf |
| model_015 | model_explain | 为什么模型不应该自动决定生产切换？ | rag_expectation_ok, top_k_title_hit, answer_point_hit | 0 |  |
| strategy_003 | trading_strategy | 低价窗口应该如何利用？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| strategy_004 | trading_strategy | 峰谷价差大是不是一定有套利机会？ | answer_point_hit | 5 | peak_valley_spread_strategy; prediction_interval_explanation; AI-项目进展与分析 (6) |
| strategy_005 | trading_strategy | 异常价格出现时应该先做什么？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| strategy_006 | trading_strategy | 储能放电策略要结合哪些限制？ | top_k_title_hit | 5 | 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》; 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf; 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》 |
| strategy_007 | trading_strategy | 售电公司做日前报价前应该复核哪些内容？ | top_k_title_hit | 5 | 河北南部电网电力市场信息披露实施细则.pdf-W020260122360751964570.pdf; 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf; 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf |
| strategy_008 | trading_strategy | 价格风险高时应该如何处理客户合约敞口？ | top_k_title_hit | 5 | AI-项目进展与分析 (4); 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知; 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf |
| strategy_009 | trading_strategy | 负价是不是一定可以买入？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| strategy_010 | trading_strategy | 高价预测和储能套利之间有什么关系？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, answer_point_hit | 0 |  |
| strategy_011 | trading_strategy | 交易建议为什么不能等同于交易指令？ | top_k_title_hit | 5 | 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf; 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf; 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知 |
| strategy_012 | trading_strategy | 实时市场偏差会影响储能策略吗？ | top_k_title_hit | 5 | AI-项目进展与分析 (9); 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知; 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知 |
| strategy_013 | trading_strategy | 如果连续低价时段出现，采购策略要注意什么？ | rag_expectation_ok, tool_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
| strategy_015 | trading_strategy | 异常价格可能是数据问题还是交易机会？ | top_k_title_hit | 5 | 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf; 河北南部电网电力中长期市场实施细则.pdf-W020260122360751859476.pdf; 河北南部电网电力中长期市场实施细则.pdf-W020260122360751859476.pdf |
| system_001 | system_usage | 这个系统是做什么的？ | top_k_title_hit | 5 | 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知; 中国绿色电力证书发展报告（2025）; 山东省虚拟电厂建设运行管理办法（征求意见稿）-downfile.jsp_classid=0&filename=28397e5c97a548b4ade4ac81e7ec6ec1.pdf |
| system_003 | system_usage | AI 助手能帮我分析什么？ | rag_expectation_ok, top_k_title_hit, answer_point_hit | 0 |  |
| system_004 | system_usage | 开发者模式能看到什么？ | rag_expectation_ok, top_k_title_hit, keyword_hit, answer_point_hit | 0 |  |
