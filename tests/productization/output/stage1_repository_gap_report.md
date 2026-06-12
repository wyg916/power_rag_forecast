# Stage1 Repository Gap 报告

- 总体状态：`stage1_gap_known`
- 统计：{"postgresql_ready": 6, "postgresql_path_ready_pending_data": 0, "pending_schema_or_data_migration": 0, "fallback_only": 0}

| 领域 | 状态 | repository 可导入 | 表状态 | 建议 |
| --- | --- | --- | --- | --- |
| weather_data | postgresql_ready | True | raw_weather[migration=True, runtime=True] | Keep PostgreSQL as the first path and keep legacy fallback disabled in production. |
| load_data | postgresql_ready | True | raw_load[migration=True, runtime=True], raw_forecast_load_selected[migration=False, runtime=True] | Keep PostgreSQL as the first path and keep legacy fallback disabled in production. |
| market_data | postgresql_ready | True | raw_market[migration=True, runtime=True], raw_da_price[migration=False, runtime=True] | Keep PostgreSQL as the first path and keep legacy fallback disabled in production. |
| renewable_data | postgresql_ready | True | raw_renewable[migration=True, runtime=True], raw_renewable_forecast[migration=False, runtime=False], raw_solar_forecast[migration=False, runtime=False], raw_wind_forecast[migration=False, runtime=False] | Keep PostgreSQL as the first path and keep legacy fallback disabled in production. |
| feature_importance | postgresql_ready | True | model_feature_importance[migration=False, runtime=True], feature_importance[migration=True, runtime=True] | Keep PostgreSQL as the first path and keep legacy fallback disabled in production. |
| report_review | postgresql_ready | True | report_reviews[migration=True, runtime=True] | Keep PostgreSQL as the first path and keep legacy fallback disabled in production. |
