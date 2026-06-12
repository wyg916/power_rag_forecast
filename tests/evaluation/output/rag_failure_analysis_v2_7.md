# v2.7 RAG 失败案例分析

- 使用报告：`tests\evaluation\output\after_knowledge_import_restart_report.json`
- 重启前通过率：42/100 (42.00%)
- 重启后通过率：40/100 (40.00%)
- 重启前 RAG 期望命中率：68.89%
- 重启后 RAG 期望命中率：68.89%
- 默认隐藏调试字段：100.00%
- cache 影响判断：重启后通过率未恢复，RAG 期望命中率持平，cache 不是主要原因。

## 失败类型统计

| 类型 | 数量 |
|---|---:|
| 未触发 RAG | 28 |
| 答案关键词不匹配 | 21 |
| RAG 触发但未召回正确文档 | 16 |
| 工具触发不符合预期 | 9 |
| Top-K 有证据但回答没有覆盖答案要点 | 8 |
| 其他 | 5 |
| 评测标题别名不匹配 | 2 |

## 分类失败统计

| 分类 | 失败数 |
|---|---:|
| price_forecast | 16 |
| trading_strategy | 12 |
| model_explain | 9 |
| system_usage | 7 |
| daily_chat | 6 |
| load_weather | 5 |
| spike_risk | 5 |

## 未触发 RAG 的问题清单

| ID | 分类 | 问题 | 建议 |
|---|---|---|---|
| price_002 | price_forecast | 明天哪些小时价格可能偏高？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| price_005 | price_forecast | 如果模型预测晚高峰价格高，我应该先看什么指标？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| price_006 | price_forecast | 预测区间变宽说明什么？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| price_007 | price_forecast | 为什么有些小时预测价格接近零？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| price_009 | price_forecast | 明天电价均价高不高？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| price_016 | price_forecast | 低价窗口是否一定适合采购？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| price_018 | price_forecast | 如果预测数据不足，AI 助手应该如何说明？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| weather_011 | load_weather | 温度升高时应该关注哪些预测字段？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| spike_003 | spike_risk | 为什么晚高峰容易出现尖峰价格？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| spike_009 | spike_risk | 尖峰价格预测偏差为什么经常更大？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| spike_010 | spike_risk | 如何判断一个高价小时是不是异常价格？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| model_005 | model_explain | 真实值回填不足时能判断模型好坏吗？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| model_006 | model_explain | 模型漂移可能由哪些因素造成？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| model_008 | model_explain | 模型版本变化会影响预测口径吗？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| model_009 | model_explain | 数据质量问题会怎样影响模型预测？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| model_010 | model_explain | 模型训练流程大概包括哪些步骤？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| model_015 | model_explain | 为什么模型不应该自动决定生产切换？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| strategy_003 | trading_strategy | 低价窗口应该如何利用？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| strategy_005 | trading_strategy | 异常价格出现时应该先做什么？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| strategy_009 | trading_strategy | 负价是不是一定可以买入？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| strategy_010 | trading_strategy | 高价预测和储能套利之间有什么关系？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| strategy_013 | trading_strategy | 如果连续低价时段出现，采购策略要注意什么？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| system_003 | system_usage | AI 助手能帮我分析什么？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| system_004 | system_usage | 开发者模式能看到什么？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| system_005 | system_usage | 为什么普通模式不显示工具调用？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| system_006 | system_usage | 预测中心和策略中心分别看什么？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| system_008 | system_usage | 如果没有预测数据，系统应该怎么提示？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| system_009 | system_usage | 模型运维页面主要关注什么？ | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |

## RAG 触发但未命中期望标题/别名的问题清单

| ID | 分类 | 问题 | Top-K标题 | 期望标题 | 类型 |
|---|---|---|---|---|---|
| price_001 | price_forecast | 明天电价风险大吗？ | AI-项目进展与分析 (11)?AI-项目进展与分析?河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知 | price_forecast_logic?peak_spike_risk_explanation?高价风险?电价预测逻辑?prediction_interval_explanation | RAG 触发但未召回正确文档 |
| price_003 | price_forecast | 日前电价预测值能不能直接作为交易价格？ | AI-项目进展与分析 (9)?AI-项目进展与分析 (1)?AI-项目进展与分析 | price_forecast_logic?pjm_day_ahead_market?day_ahead_vs_real_time?电价预测逻辑?prediction_interval_explanation | 评测标题别名不匹配 |
| price_004 | price_forecast | 预测电价和真实结算电价为什么会有差异？ | AI-项目进展与分析?AI-项目进展与分析 (1)?AI-项目进展与分析 (10) | day_ahead_vs_real_time?forecast_error_explanation?price_forecast_logic?电价预测逻辑?prediction_interval_explanation | RAG 触发但未召回正确文档 |
| price_008 | price_forecast | 电价预测主要依赖哪些数据？ | AI-项目进展与分析 (1)?AI-项目进展与分析?AI-项目进展与分析 (5) | price_forecast_logic?data_fields_dictionary?电价预测逻辑?prediction_interval_explanation?model_pipeline_explanation | RAG 触发但未召回正确文档 |
| price_010 | price_forecast | 最高价和平均价哪个更适合判断风险？ | high_price_risk_strategy?河北南部电网电力现货市场实施细则.pdf-W020260122360751867980.pdf?河北南部电网电力市场信息披露实施细则.pdf-W020260122360751964570.pdf | risk_level_rules?price_forecast_logic?电价预测逻辑?prediction_interval_explanation?model_pipeline_explanation | RAG 触发但未召回正确文档 |
| price_012 | price_forecast | 实时市场变化会怎样影响日前预测判断？ | AI-项目进展与分析 (9)?河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知?河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知 | day_ahead_vs_real_time?pjm_day_ahead_market?price_forecast_logic?电价预测逻辑?prediction_interval_explanation | RAG 触发但未召回正确文档 |
| price_015 | price_forecast | 电价突然跳高时先判断模型问题还是市场问题？ | AI-项目进展与分析?AI-项目进展与分析 (5)?河北省发展和改革委员会关于优化调整河北南网工商业及其他用户分时电价政策的通知 | abnormal_price_response?forecast_error_explanation?price_forecast_logic?电价预测逻辑?prediction_interval_explanation | RAG 触发但未召回正确文档 |
| price_017 | price_forecast | 电价预测结果里的风险等级应该怎么用？ | AI-项目进展与分析?AI-项目进展与分析 (1)?AI-项目进展与分析 (9) | risk_level_rules?风险等级定义?price_forecast_logic?电价预测逻辑?prediction_interval_explanation | RAG 触发但未召回正确文档 |
| price_019 | price_forecast | 价格预测可信度要结合哪些因素判断？ | AI-项目进展与分析 (1)?AI-项目进展与分析 (9)?河北南部电网电力现货市场实施细则.pdf-W020260122360751867980.pdf | forecast_error_explanation?price_forecast_logic?电价预测逻辑?prediction_interval_explanation?model_pipeline_explanation | RAG 触发但未召回正确文档 |
| model_004 | model_explain | MAE 和 RMSE 在电价预测里怎么理解？ | 国家发展改革委关于降低燃煤发电上网电价?国家发展改革委关于降低燃煤发电上网电价和一般工商业用电价格的通知 (发改价格〔2015〕3105号)?电价预测逻辑说明 | forecast_error_explanation?prediction_interval_explanation?model_pipeline_explanation?model_retrain_rules?risk_level_rules | RAG 触发但未召回正确文档 |
| model_013 | model_explain | 特征工程变化会导致预测结果变化吗？ | 新型储能电站建设工程质量监督大纲-9296ad160ac140888b20dbc4d54ae917.pdf?新型储能电站建设工程质量监督大纲-9296ad160ac140888b20dbc4d54ae917.pdf?新型储能电站建设工程质量监督大纲-9296ad160ac140888b20dbc4d54ae917.pdf | model_pipeline_explanation?forecast_error_explanation?prediction_interval_explanation?model_retrain_rules?risk_level_rules | RAG 触发但未召回正确文档 |
| strategy_006 | trading_strategy | 储能放电策略要结合哪些限制？ | 省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》?华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf?省发展改革委 省工业和信息化厅联合印发《关于支持新型储能健康发展的通知》 | high_price_risk_strategy?peak_valley_spread_strategy?low_price_opportunity_strategy?abnormal_price_response?trading_strategy | 评测标题别名不匹配 |
| strategy_007 | trading_strategy | 售电公司做日前报价前应该复核哪些内容？ | 河北南部电网电力市场信息披露实施细则.pdf-W020260122360751964570.pdf?华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf?华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf | high_price_risk_strategy?pjm_day_ahead_market?low_price_opportunity_strategy?peak_valley_spread_strategy?abnormal_price_response | RAG 触发但未召回正确文档 |
| strategy_008 | trading_strategy | 价格风险高时应该如何处理客户合约敞口？ | AI-项目进展与分析 (4)?河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知?华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf | high_price_risk_strategy?low_price_opportunity_strategy?peak_valley_spread_strategy?abnormal_price_response?trading_strategy | RAG 触发但未召回正确文档 |
| strategy_011 | trading_strategy | 交易建议为什么不能等同于交易指令？ | 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf?华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf?河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知 | ai_assistant_answer_rules?risk_level_rules?high_price_risk_strategy?low_price_opportunity_strategy?peak_valley_spread_strategy | RAG 触发但未召回正确文档 |
| strategy_012 | trading_strategy | 实时市场偏差会影响储能策略吗？ | AI-项目进展与分析 (9)?河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知?河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知 | day_ahead_vs_real_time?peak_valley_spread_strategy?high_price_risk_strategy?low_price_opportunity_strategy?abnormal_price_response | RAG 触发但未召回正确文档 |
| strategy_015 | trading_strategy | 异常价格可能是数据问题还是交易机会？ | 华中区域（东四省）电力互济交易实施细则.pdf-华中区域（东四省）电力互济交易实施细则.pdf?河北南部电网电力中长期市场实施细则.pdf-W020260122360751859476.pdf?河北南部电网电力中长期市场实施细则.pdf-W020260122360751859476.pdf | abnormal_price_response?high_price_risk_strategy?low_price_opportunity_strategy?peak_valley_spread_strategy?trading_strategy | RAG 触发但未召回正确文档 |
| system_001 | system_usage | 这个系统是做什么的？ | 河北省发展和改革委员会国家能源局华北监管局关于印发《河北南部电网电力市场运行规则》及配套实施细则的通知?中国绿色电力证书发展报告（2025）?山东省虚拟电厂建设运行管理办法（征求意见稿）-downfile.jsp_classid=0&filename=28397e5c97a548b4ade4ac81e7ec6ec1.pdf | system_overview?data_fields_dictionary?ai_assistant_answer_rules?model_pipeline_explanation?系统概览 | RAG 触发但未召回正确文档 |

## Top-K 有证据但答案没覆盖要点的问题清单

| ID | 分类 | 问题 | 缺失要点 | Top-K标题 |
|---|---|---|---|---|
| weather_005 | load_weather | 负荷和电价之间是线性关系吗？ | 不是简单线性?供给?约束 | AI-项目进展与分析 (5)?AI-项目进展与分析?AI-项目进展与分析 (6) |
| weather_007 | load_weather | 天气预报误差会不会放大电价预测误差？ | 会影响?负荷偏差?模型误差 | 天气与电价关系?forecast_error_explanation?price_forecast_logic |
| weather_012 | load_weather | 天气数据不新鲜会影响 AI 助手判断吗？ | 会影响?数据时间?限制 | 负荷、天气与电价关系?模型流程说明?模型重训判断规则 |
| weather_013 | load_weather | 负荷高但电价没涨可能是什么原因？ | 供给充裕?拥塞?报价 | AI-项目进展与分析 (5)?AI-项目进展与分析 (6)?AI-项目进展与分析 |
| spike_001 | spike_risk | 尖峰概率高是不是一定代表价格会暴涨？ | 不是必然?风险概率?结合负荷 | peak_spike_risk_explanation?AI-项目进展与分析 (1)?risk_level_rules |
| spike_013 | spike_risk | 如果明天连续多个小时尖峰风险高，应该怎么处理？ | 连续窗口?敞口?预案 | AI-项目进展与分析 (11)?peak_valley_spread_strategy?model_retrain_rules |
| model_007 | model_explain | 高价时段误差大该不该马上切换模型？ | 不应马上?回测?复核 | high_price_risk_strategy?forecast_error_explanation?peak_valley_spread_strategy |
| strategy_004 | trading_strategy | 峰谷价差大是不是一定有套利机会？ | 不一定?效率?约束 | peak_valley_spread_strategy?prediction_interval_explanation?AI-项目进展与分析 (6) |

## 全量失败明细

| ID | 分类 | 问题 | 失败类型 | RAG命中 | 失败检查 | 建议修复 |
|---|---|---|---|---:|---|---|
| price_001 | price_forecast | 明天电价风险大吗？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| price_002 | price_forecast | 明天哪些小时价格可能偏高？ | 未触发 RAG?答案关键词不匹配?工具触发不符合预期 | 0 | rag_expectation_ok?tool_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| price_003 | price_forecast | 日前电价预测值能不能直接作为交易价格？ | 评测标题别名不匹配 | 5 | top_k_title_hit | 增加 title alias 映射，把长标题、类别名和评测短标题打通。 |
| price_004 | price_forecast | 预测电价和真实结算电价为什么会有差异？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| price_005 | price_forecast | 如果模型预测晚高峰价格高，我应该先看什么指标？ | 未触发 RAG?答案关键词不匹配?工具触发不符合预期 | 0 | rag_expectation_ok?tool_expectation_ok?top_k_title_hit?keyword_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| price_006 | price_forecast | 预测区间变宽说明什么？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| price_007 | price_forecast | 为什么有些小时预测价格接近零？ | 未触发 RAG?答案关键词不匹配?工具触发不符合预期 | 0 | rag_expectation_ok?tool_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| price_008 | price_forecast | 电价预测主要依赖哪些数据？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| price_009 | price_forecast | 明天电价均价高不高？ | 未触发 RAG | 0 | rag_expectation_ok?top_k_title_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| price_010 | price_forecast | 最高价和平均价哪个更适合判断风险？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| price_012 | price_forecast | 实时市场变化会怎样影响日前预测判断？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| price_015 | price_forecast | 电价突然跳高时先判断模型问题还是市场问题？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| price_016 | price_forecast | 低价窗口是否一定适合采购？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| price_017 | price_forecast | 电价预测结果里的风险等级应该怎么用？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| price_018 | price_forecast | 如果预测数据不足，AI 助手应该如何说明？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| price_019 | price_forecast | 价格预测可信度要结合哪些因素判断？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| weather_005 | load_weather | 负荷和电价之间是线性关系吗？ | Top-K 有证据但回答没有覆盖答案要点 | 5 | answer_point_hit | 增强 Prompt 对 evidence 的使用约束，要求覆盖结论、依据、建议和评测要点。 |
| weather_007 | load_weather | 天气预报误差会不会放大电价预测误差？ | Top-K 有证据但回答没有覆盖答案要点 | 5 | answer_point_hit | 增强 Prompt 对 evidence 的使用约束，要求覆盖结论、依据、建议和评测要点。 |
| weather_011 | load_weather | 温度升高时应该关注哪些预测字段？ | 未触发 RAG?答案关键词不匹配?工具触发不符合预期 | 0 | rag_expectation_ok?tool_expectation_ok?top_k_title_hit?keyword_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| weather_012 | load_weather | 天气数据不新鲜会影响 AI 助手判断吗？ | Top-K 有证据但回答没有覆盖答案要点 | 5 | answer_point_hit | 增强 Prompt 对 evidence 的使用约束，要求覆盖结论、依据、建议和评测要点。 |
| weather_013 | load_weather | 负荷高但电价没涨可能是什么原因？ | Top-K 有证据但回答没有覆盖答案要点 | 5 | answer_point_hit | 增强 Prompt 对 evidence 的使用约束，要求覆盖结论、依据、建议和评测要点。 |
| spike_001 | spike_risk | 尖峰概率高是不是一定代表价格会暴涨？ | Top-K 有证据但回答没有覆盖答案要点 | 5 | answer_point_hit | 增强 Prompt 对 evidence 的使用约束，要求覆盖结论、依据、建议和评测要点。 |
| spike_003 | spike_risk | 为什么晚高峰容易出现尖峰价格？ | 未触发 RAG?答案关键词不匹配?工具触发不符合预期 | 0 | rag_expectation_ok?tool_expectation_ok?top_k_title_hit?keyword_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| spike_009 | spike_risk | 尖峰价格预测偏差为什么经常更大？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| spike_010 | spike_risk | 如何判断一个高价小时是不是异常价格？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| spike_013 | spike_risk | 如果明天连续多个小时尖峰风险高，应该怎么处理？ | Top-K 有证据但回答没有覆盖答案要点 | 5 | answer_point_hit | 增强 Prompt 对 evidence 的使用约束，要求覆盖结论、依据、建议和评测要点。 |
| model_004 | model_explain | MAE 和 RMSE 在电价预测里怎么理解？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| model_005 | model_explain | 真实值回填不足时能判断模型好坏吗？ | 未触发 RAG?工具触发不符合预期 | 0 | rag_expectation_ok?tool_expectation_ok?top_k_title_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| model_006 | model_explain | 模型漂移可能由哪些因素造成？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| model_007 | model_explain | 高价时段误差大该不该马上切换模型？ | Top-K 有证据但回答没有覆盖答案要点 | 5 | answer_point_hit | 增强 Prompt 对 evidence 的使用约束，要求覆盖结论、依据、建议和评测要点。 |
| model_008 | model_explain | 模型版本变化会影响预测口径吗？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| model_009 | model_explain | 数据质量问题会怎样影响模型预测？ | 未触发 RAG | 0 | rag_expectation_ok?top_k_title_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| model_010 | model_explain | 模型训练流程大概包括哪些步骤？ | 未触发 RAG | 0 | rag_expectation_ok?top_k_title_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| model_013 | model_explain | 特征工程变化会导致预测结果变化吗？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| model_015 | model_explain | 为什么模型不应该自动决定生产切换？ | 未触发 RAG | 0 | rag_expectation_ok?top_k_title_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| strategy_003 | trading_strategy | 低价窗口应该如何利用？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| strategy_004 | trading_strategy | 峰谷价差大是不是一定有套利机会？ | Top-K 有证据但回答没有覆盖答案要点 | 5 | answer_point_hit | 增强 Prompt 对 evidence 的使用约束，要求覆盖结论、依据、建议和评测要点。 |
| strategy_005 | trading_strategy | 异常价格出现时应该先做什么？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| strategy_006 | trading_strategy | 储能放电策略要结合哪些限制？ | 评测标题别名不匹配 | 5 | top_k_title_hit | 增加 title alias 映射，把长标题、类别名和评测短标题打通。 |
| strategy_007 | trading_strategy | 售电公司做日前报价前应该复核哪些内容？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| strategy_008 | trading_strategy | 价格风险高时应该如何处理客户合约敞口？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| strategy_009 | trading_strategy | 负价是不是一定可以买入？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| strategy_010 | trading_strategy | 高价预测和储能套利之间有什么关系？ | 未触发 RAG?工具触发不符合预期 | 0 | rag_expectation_ok?tool_expectation_ok?top_k_title_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| strategy_011 | trading_strategy | 交易建议为什么不能等同于交易指令？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| strategy_012 | trading_strategy | 实时市场偏差会影响储能策略吗？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| strategy_013 | trading_strategy | 如果连续低价时段出现，采购策略要注意什么？ | 未触发 RAG?答案关键词不匹配?工具触发不符合预期 | 0 | rag_expectation_ok?tool_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 检查 intent_router 和 tools_for_intent 的工具映射。 |
| strategy_015 | trading_strategy | 异常价格可能是数据问题还是交易机会？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| system_001 | system_usage | 这个系统是做什么的？ | RAG 触发但未召回正确文档 | 5 | top_k_title_hit | 增加 query rewrite、领域同义词和 category boost，提高期望文档召回率。 |
| system_003 | system_usage | AI 助手能帮我分析什么？ | 未触发 RAG | 0 | rag_expectation_ok?top_k_title_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 |
| system_004 | system_usage | 开发者模式能看到什么？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| system_005 | system_usage | 为什么普通模式不显示工具调用？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| system_006 | system_usage | 预测中心和策略中心分别看什么？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| system_008 | system_usage | 如果没有预测数据，系统应该怎么提示？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit?answer_point_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| system_009 | system_usage | 模型运维页面主要关注什么？ | 未触发 RAG?答案关键词不匹配 | 0 | rag_expectation_ok?top_k_title_hit?keyword_hit | 增强专业领域词 RAG 触发规则，避免专业问题被跳过。 在 prompt 或 guard 中保留关键业务词，同时复核评测关键词是否过窄。 |
| daily_002 | daily_chat | 你是谁？ | 其他 | 0 | answer_point_hit | 人工复核该失败样例。 |
| daily_003 | daily_chat | 你好 | 其他 | 0 | answer_point_hit | 人工复核该失败样例。 |
| daily_004 | daily_chat | 谢谢你 | 其他 | 0 | answer_point_hit | 人工复核该失败样例。 |
| daily_006 | daily_chat | 早上好 | 其他 | 0 | answer_point_hit | 人工复核该失败样例。 |
| daily_007 | daily_chat | 现在几点？ | 工具触发不符合预期 | 0 | tool_expectation_ok?answer_point_hit | 检查 intent_router 和 tools_for_intent 的工具映射。 |
| daily_009 | daily_chat | 请用一句话回答 | 其他 | 0 | answer_point_hit | 人工复核该失败样例。 |
