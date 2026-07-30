# PostgreSQL 主事实源验收报告

- 项目路径：`E:\智能运营分析项目`
- 总体状态：`pass_with_warnings`
- Repository 可导入：是
- 核心模块静态引用 repository：是
- Alembic 静态检查：通过
- 运行时旧数据源主路径/部分主路径引用数：95

## Repository 可导入性
| 领域 | 模块 | 可导入 | 错误 |
| --- | --- | --- | --- |
| forecast | backend.app.repositories.forecast_repository | 是 |  |
| model | backend.app.repositories.model_repository | 是 |  |
| task | backend.app.repositories.task_repository | 是 |  |
| report | backend.app.repositories.report_repository | 是 |  |
| ai_trace | backend.app.repositories.ai_trace_repository | 是 |  |
| audit | backend.app.repositories.audit_repository | 是 |  |
| knowledge | backend.app.repositories.knowledge_repository | 是 |  |

## 核心模块 Repository 使用情况
| 领域 | 状态 | 命中标识 |
| --- | --- | --- |
| forecast | ok | forecast_repository, load_latest_forecast |
| model | ok | model_errors_from_postgres, model_repository, model_status_from_postgres |
| task | ok | list_recent_tasks, save_task_record, task_log_text, task_repository |
| report | ok | report_repository, report_reviews, report_runs, report_status_from_postgres |
| ai_trace | ok | ai_trace_repository, get_ai_trace, list_ai_traces, save_ai_trace |
| audit | ok | audit_logs, audit_repository, write_audit_log |
| knowledge | ok | knowledge_repository, list_embedded_chunks, search_keyword_chunks |

## 旧数据源引用统计
| 模式 | 数量 |
| --- | --- |
| csv | 57 |
| excel | 45 |
| hardcoded_project_path | 2 |
| local_prediction_file | 85 |
| mysql | 15 |
| old_knowledge_direct_read | 21 |
| sqlite | 6 |

## 使用场景分类
| 场景 | 数量 |
| --- | --- |
| assistant_data_freshness_tool | 10 |
| assistant_prompt_or_evidence_label | 14 |
| documentation_or_config_hint | 7 |
| frontend_export_or_mock | 14 |
| knowledge_indexing_source | 6 |
| legacy_ai_knowledge_search | 2 |
| legacy_ai_tool_registry | 7 |
| legacy_file_or_import_path | 28 |
| migration_tool | 9 |
| platform_service_runtime | 6 |
| postgres_etl_or_bootstrap | 8 |
| postgres_first_compatibility_layer | 16 |
| repository_result_shape | 6 |
| stage1_compatibility_api | 10 |
| tariff_tool_csv_fallback | 9 |
| tariff_tool_runtime | 1 |
| test_or_evaluation_fixture | 54 |
| uncategorized_reference | 24 |

## 需要重点复核的运行时引用
| 文件 | 行 | 模式 | 场景 | 是否主路径 | PG 替代 | 建议 |
| --- | --- | --- | --- | --- | --- | --- |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 11 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 15 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 16 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 17 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 18 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 19 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 20 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 33 | mysql | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 35 | mysql | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 177 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/tariff_tools.py | 15 | old_knowledge_direct_read | tariff_tool_runtime | 部分 | 是 | 应优先读取 PostgreSQL tariff/policy 表。 |
| backend/app/api/v1/endpoints/assistant.py | 211 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| backend/app/api/v1/endpoints/knowledge.py | 35 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| backend/app/api/v1/endpoints/knowledge.py | 275 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| backend/app/api/v1/endpoints/model.py | 390 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| backend/app/data_access.py | 30 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 30 | local_prediction_file | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 31 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 84 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 92 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 94 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 215 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 222 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 223 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 224 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 225 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 226 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 227 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 427 | mysql | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 653 | local_prediction_file | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 665 | local_prediction_file | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/platform_services.py | 76 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 222 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 515 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 643 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 651 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 681 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/services/data_trust_service.py | 167 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/data_trust_service.py | 175 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/data_trust_service.py | 178 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/data_trust_service.py | 816 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/data_trust_service.py | 921 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/forecast_transaction_service.py | 75 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/forecast_transaction_service.py | 243 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/forecast_transaction_service.py | 379 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/forecast_transaction_service.py | 382 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/forecast_transaction_service.py | 384 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/task_business_handlers.py | 50 | excel | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| backend/app/services/task_business_handlers.py | 50 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| backend/app/services/ui_platform_service.py | 380 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| backend/app/stage1_services.py | 16 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 127 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 128 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 180 | local_prediction_file | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 196 | local_prediction_file | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 264 | local_prediction_file | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 277 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 315 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 345 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 398 | local_prediction_file | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| knowledge_pipeline/import_chunks_to_kb.py | 507 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| knowledge_pipeline/knowledge_batch_processor.py | 821 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| knowledge_pipeline/knowledge_batch_processor.py | 1190 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/generate_project_analysis_doc.py | 256 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_doc.py | 349 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 173 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 209 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 232 | old_knowledge_direct_read | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 237 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 274 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 275 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 332 | old_knowledge_direct_read | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 336 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 361 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 427 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/generate_project_analysis_docx.py | 442 | local_prediction_file | uncategorized_reference | 待确认 | 待确认 | 人工复核。 |
| scripts/import_stage1_raw_data_to_postgres.py | 34 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 35 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 37 | excel | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 245 | excel | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |

## Alembic 静态检查
- `alembic.ini`：存在
- `migrations/env.py`：存在
- 迁移文件：migrations/versions/0001_initial_postgres_schema.py, migrations/versions/0002_rag_rbac_audit.py, migrations/versions/0003_stage1_raw_data.py, migrations/versions/0004_task_center_enterprise.py, migrations/versions/0005_task_runtime_observability.py, migrations/versions/0006_auth_users.py, migrations/versions/0007_task_runtime_productionization.py, migrations/versions/0008_knowledge_business_closure.py, migrations/versions/0009_model_center_governance.py, migrations/versions/0010_model_prediction_comparison_points.py, migrations/versions/0011_settings_center_closure.py, migrations/versions/0012_backend_legacy_optional_tables.py, migrations/versions/0013_t001_model_fact_source.py, migrations/versions/0014_t003_run_transaction.py, migrations/versions/0015_phase5d_strategy_governance.py, migrations/versions/0016_p6_strategy_runtime_facts.py
- 核心表缺失：无
- 索引数量：135
- 空库运行检查：not_run，原因：默认脚本不读取真实 .env，也未连接外部数据库；如需实测，请在独立空库设置 DATABASE_URL 后运行 alembic upgrade head。

## 结论
- PostgreSQL 产品化骨架已覆盖预测、模型、任务、报告、AI Trace、知识库和审计等核心表。
- 主要运行时入口已出现 repository 或 PostgreSQL 优先路径；旧 Excel/CSV/本地文件仍集中在兼容接口、ETL 输入、前端导出、测试夹具和少量工具 fallback。
- 后续企业化应优先把 Stage1 天气/负荷/可再生接口和 report review 的本地 JSON fallback repository 化。
