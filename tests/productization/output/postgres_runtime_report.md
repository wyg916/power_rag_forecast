# PostgreSQL 运行态验收报告

- 状态：`pass`
- 连接：host=localhost port=5432 user=postgres db=postgres password=******
- Alembic upgrade head：已执行
- Alembic version at head：True
- 表数量：32
- 索引数量：88

## 核心表
| 表名 | 存在 |
| --- | --- |
| forecast_runs | 是 |
| forecast_results | 是 |
| model_versions | 是 |
| model_metrics | 是 |
| report_runs | 是 |
| report_reviews | 是 |
| task_runs | 是 |
| task_logs | 是 |
| ai_traces | 是 |
| audit_logs | 是 |
| kb_documents | 是 |
| kb_chunks | 是 |
| users | 是 |
| roles | 是 |
| raw_market | 是 |
| raw_weather | 是 |
| raw_load | 是 |
| raw_renewable | 是 |
| feature_importance | 是 |

## 核心索引
| 索引名 | 存在 |
| --- | --- |
| idx_forecast_results_run_id | 是 |
| idx_forecast_results_datetime | 是 |
| idx_model_metrics_version | 是 |
| idx_task_runs_status | 是 |
| idx_task_runs_execution_mode | 是 |
| idx_task_runs_cancel_requested | 是 |
| idx_task_runs_celery_task_id | 是 |
| idx_task_logs_task_id | 是 |
| idx_ai_traces_session | 是 |
| idx_report_runs_run_id | 是 |
| idx_kb_chunks_doc_id | 是 |
| idx_audit_logs_action | 是 |
| idx_users_role_id | 是 |
| idx_raw_market_datetime | 是 |
| idx_raw_weather_datetime | 是 |
| idx_raw_load_datetime | 是 |
| idx_raw_renewable_datetime | 是 |
| idx_feature_importance_rank | 是 |
