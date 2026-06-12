# PostgreSQL 主事实源验收报告

- 项目路径：`E:\智能运营分析项目`
- 总体状态：`pass_with_warnings`
- Repository 可导入：是
- 核心模块静态引用 repository：是
- Alembic 静态检查：通过
- 运行时旧数据源主路径/部分主路径引用数：60

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
| forecast | ok | forecast_repository, load_latest_forecast, load_latest_forecast_from_postgres |
| model | ok | model_errors_from_postgres, model_repository, model_status_from_postgres |
| task | ok | list_recent_tasks, save_task_record, task_log_text, task_repository |
| report | ok | report_repository, report_reviews, report_status_from_postgres |
| ai_trace | ok | ai_trace_repository, get_ai_trace, list_ai_traces, save_ai_trace |
| audit | ok | audit_logs, audit_repository, write_audit_log |
| knowledge | ok | knowledge_repository, list_embedded_chunks, search_keyword_chunks |

## 旧数据源引用统计
| 模式 | 数量 |
| --- | --- |
| csv | 31 |
| excel | 41 |
| hardcoded_project_path | 7 |
| local_prediction_file | 48 |
| mysql | 15 |
| old_knowledge_direct_read | 21 |
| sqlite | 1 |

## 使用场景分类
| 场景 | 数量 |
| --- | --- |
| assistant_data_freshness_tool | 10 |
| assistant_knowledge_tool_source | 4 |
| assistant_prompt_or_evidence_label | 16 |
| documentation_or_config_hint | 13 |
| frontend_export_or_mock | 7 |
| knowledge_indexing_source | 6 |
| legacy_ai_knowledge_search | 2 |
| legacy_ai_tool_registry | 7 |
| legacy_file_or_import_path | 11 |
| migration_tool | 9 |
| platform_service_runtime | 6 |
| postgres_etl_or_bootstrap | 8 |
| postgres_first_compatibility_layer | 18 |
| stage1_compatibility_api | 10 |
| tariff_tool_csv_fallback | 9 |
| tariff_tool_runtime | 1 |
| test_or_evaluation_fixture | 27 |

## 需要重点复核的运行时引用
| 文件 | 行 | 模式 | 场景 | 是否主路径 | PG 替代 | 建议 |
| --- | --- | --- | --- | --- | --- | --- |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 9 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 13 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 14 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 15 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 16 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 17 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 18 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 31 | mysql | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 33 | mysql | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/data_freshness_tools.py | 53 | excel | assistant_data_freshness_tool | 部分 | 是 | 数据库优先，Excel freshness 作为兼容兜底。 |
| backend/app/ai_assistant/tools/knowledge_tools.py | 11 | old_knowledge_direct_read | assistant_knowledge_tool_source | 部分 | 是 | 确认工具优先调用 RAG/repository；本地文件仅作为索引或兜底。 |
| backend/app/ai_assistant/tools/knowledge_tools.py | 12 | old_knowledge_direct_read | assistant_knowledge_tool_source | 部分 | 是 | 确认工具优先调用 RAG/repository；本地文件仅作为索引或兜底。 |
| backend/app/ai_assistant/tools/knowledge_tools.py | 13 | old_knowledge_direct_read | assistant_knowledge_tool_source | 部分 | 是 | 确认工具优先调用 RAG/repository；本地文件仅作为索引或兜底。 |
| backend/app/ai_assistant/tools/knowledge_tools.py | 67 | old_knowledge_direct_read | assistant_knowledge_tool_source | 部分 | 是 | 确认工具优先调用 RAG/repository；本地文件仅作为索引或兜底。 |
| backend/app/ai_assistant/tools/tariff_tools.py | 15 | old_knowledge_direct_read | tariff_tool_runtime | 部分 | 是 | 应优先读取 PostgreSQL tariff/policy 表。 |
| backend/app/data_access.py | 30 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 30 | local_prediction_file | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 31 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 84 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 92 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 94 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 149 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 155 | local_prediction_file | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 231 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 237 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 238 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 239 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 240 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 241 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 242 | excel | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 437 | mysql | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 651 | local_prediction_file | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/data_access.py | 663 | local_prediction_file | postgres_first_compatibility_layer | 部分 | 是 | 保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。 |
| backend/app/platform_services.py | 54 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 168 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 446 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 541 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 549 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/platform_services.py | 560 | local_prediction_file | platform_service_runtime | 部分 | 部分 | 预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。 |
| backend/app/services/ui_platform_service.py | 102 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| backend/app/stage1_services.py | 16 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 127 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 128 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 185 | local_prediction_file | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 191 | local_prediction_file | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 246 | local_prediction_file | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 259 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 297 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 327 | excel | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| backend/app/stage1_services.py | 380 | local_prediction_file | stage1_compatibility_api | 部分 | 部分 | 预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。 |
| knowledge_pipeline/import_chunks_to_kb.py | 337 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| knowledge_pipeline/knowledge_batch_processor.py | 821 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| knowledge_pipeline/knowledge_batch_processor.py | 1190 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 31 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 32 | csv | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 34 | excel | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 204 | excel | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 214 | excel | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 215 | excel | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |
| scripts/import_stage1_raw_data_to_postgres.py | 216 | excel | legacy_file_or_import_path | 部分 | 待确认 | 检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。 |

## Alembic 静态检查
- `alembic.ini`：存在
- `migrations/env.py`：存在
- 迁移文件：migrations/versions/0001_initial_postgres_schema.py, migrations/versions/0002_rag_rbac_audit.py, migrations/versions/0003_stage1_raw_data.py, migrations/versions/0004_task_center_enterprise.py
- 核心表缺失：无
- 索引数量：48
- 空库运行检查：not_run，原因：默认脚本不读取真实 .env，也未连接外部数据库；如需实测，请在独立空库设置 DATABASE_URL 后运行 alembic upgrade head。

## 结论
- PostgreSQL 产品化骨架已覆盖预测、模型、任务、报告、AI Trace、知识库和审计等核心表。
- 主要运行时入口已出现 repository 或 PostgreSQL 优先路径；旧 Excel/CSV/本地文件仍集中在兼容接口、ETL 输入、前端导出、测试夹具和少量工具 fallback。
- 后续企业化应优先把 Stage1 天气/负荷/可再生接口和 report review 的本地 JSON fallback repository 化。
