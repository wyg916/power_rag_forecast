# PostgreSQL 迁移影响清单

生成时间：2026-05-31

当前阶段：任务01 - 项目扫描与迁移影响清单

本文件基于 `AI售电交易决策平台_PostgreSQL迁移与产品化优化落地方案_Codex执行版.docx` 的任务01要求生成。本阶段只做扫描与影响清单，不修改业务逻辑。

## 1. 执行结论

当前项目仍以 MySQL 作为数据库实现，核心数据库能力集中在 `database_utils.py`，业务层大量通过 `apply_database_migrations()`、`create_database_engine()`、`get_database_config()` 间接访问 MySQL。后端 Web、模型运维、AI Trace、报告、任务、旧版 GUI 服务均存在 MySQL 依赖。

迁移到 PostgreSQL 不能只替换连接字符串，原因如下：

- 当前连接 URL 写死为 `mysql+pymysql://...`。
- SQL 标识符大量使用 MySQL 反引号。
- 迁移脚本位于 `migrations/*.sql`，语法是 MySQL 风格。
- 代码中存在 MySQL 专用语法，例如 `CREATE DATABASE IF NOT EXISTS ... CHARACTER SET ... COLLATE ...`、`ON DUPLICATE KEY UPDATE`、`GROUP_CONCAT(... SEPARATOR ', ')`、`SHOW`/`DATABASE()` 语义、`AUTO_INCREMENT`、`TINYINT`、`LONGTEXT`。
- 当前配置使用 `DB_HOST`、`DB_USER`、`DB_PASSWORD`、`DB_NAME` 等拆分参数，尚未以 `DATABASE_URL` 作为统一入口。
- 当前没有 Alembic 配置，也没有 PostgreSQL 基线 migration。
- 当前没有 Celery/Redis 任务队列依赖，耗时任务仍由脚本或 `TaskManager` 子进程方式触发。

## 2. 当前数据库相关配置

| 文件 | 当前状态 | 迁移影响 |
|---|---|---|
| `.env.example` | 以 MySQL 为主，包含 `DB_HOST`、`DB_PORT=3306`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`、`DB_CHARSET` | 任务02应新增 `DATABASE_URL`、`REDIS_URL`，旧字段保留兼容但不作为主入口 |
| `llm_service_config.yaml` | `database` 节点保存 MySQL host/port/user/password/database/charset | 任务02应由 `backend/app/core/config.py` 统一读取，逐步降级为兼容配置 |
| `config_loader.py` | `apply_env_overrides()` 读取 `DB_*` 并写入 `config["database"]` | 需要支持 `DATABASE_URL` 优先，避免业务代码继续感知 DB_HOST/DB_USER/DB_PASSWORD |
| `requirements.txt` | 包含 `SQLAlchemy`、`pymysql`；未包含 `psycopg`、`alembic`、`celery`、`redis` | 任务02增加 PostgreSQL 驱动和 Alembic；Celery/Redis应到任务07再引入 |

## 3. MySQL 依赖位置清单

### 3.1 数据库核心工具

| 文件 | 依赖点 | 说明 | PostgreSQL 迁移风险 |
|---|---|---|---|
| `database_utils.py` | `DatabaseConfig` | 当前字段是 MySQL 风格：host/port/user/password/database/charset | 需要新增 URL 配置模型，避免业务代码拼接连接参数 |
| `database_utils.py` | `_server_url()`、`_database_url()` | 写死 `mysql+pymysql://` | 任务02必须改为 `DATABASE_URL` 驱动，旧 MySQL URL 仅用于迁移脚本 |
| `database_utils.py` | `_quote_identifier()` | 使用反引号 `` ` `` | PostgreSQL 需要双引号或 SQLAlchemy dialect-aware quote |
| `database_utils.py` | `ensure_database_ready()` | 使用 `CREATE DATABASE IF NOT EXISTS`、`CHARACTER SET`、`COLLATE` | PostgreSQL 不支持同样语法；生产不建议应用启动时自动建库 |
| `database_utils.py` | `apply_database_migrations()` | 执行 `migrations/*.sql` 的 MySQL SQL，并写 `schema_migrations` | 后续应由 Alembic 管理 PostgreSQL；旧函数保留用于 MySQL 迁移兼容 |
| `database_utils.py` | `write_dataframe()` / `sync_*_to_database()` | pandas `to_sql()` 写入 MySQL 表 | PostgreSQL 仍可使用，但 JSON 字段和类型映射需调整 |
| `database_utils.py` | `list_database_browse_sources()` / `preview_relation()` | MySQL 表/视图浏览、标识符 quoting | 需要 repository 或 db utility 统一适配 PostgreSQL |
| `database_utils.py` | `_ensure_primary_key()`、`_ensure_indexes()`、`_ensure_views()` | 动态补主键、索引、视图，使用 MySQL 元数据和 DDL | PostgreSQL 应转为 Alembic migration，不建议运行期修改结构 |

### 3.2 FastAPI 后端

| 文件 | 依赖点 | 说明 | PostgreSQL 迁移风险 |
|---|---|---|---|
| `backend/app/data_access.py` | `database_engine()` | 通过 `create_database_engine(project_config())` 获取 MySQL engine | 任务04/06应改为 repository + PostgreSQL session |
| `backend/app/data_access.py` | `query_dataframe()` | 直接执行 SQL 文本 | 需要迁移到 repositories，保留 Excel fallback |
| `backend/app/data_access.py` | `database_table_status()` | SQL 使用反引号 | PostgreSQL 不兼容 |
| `backend/app/data_access.py` | `database_tables()` | 查询 MySQL `information_schema.TABLES/COLUMNS`，使用 `DATABASE()` 和 `GROUP_CONCAT(... SEPARATOR ', ')` | PostgreSQL 需要 `current_schema()`、`string_agg()` 或 SQLAlchemy inspector |
| `backend/app/platform_services.py` | `_insert_rows()` | 直接调用 pandas `to_sql()` 写策略/异常表 | 应改为 repository，JSON 证据字段迁移为 JSONB |
| `backend/app/platform_services.py` | `generate_ai_insights()` | 直接 SQL 查询 `prediction_tracking` | 应改为 model/forecast repository |
| `backend/app/task_manager.py` | `_save_analysis_run()` | 执行迁移并写 `analysis_runs`、`task_logs` | 第一阶段保留；任务07应替换为 Celery + task_runs/task_logs |
| `backend/app/services/core_data_sync.py` | `_engine_or_none()` | 执行 MySQL migrations 后创建 MySQL engine | PostgreSQL 迁移第一批重点文件 |
| `backend/app/services/core_data_sync.py` | `_replace_table()` | 使用 `DELETE FROM \`table\`` + pandas `to_sql()` | PostgreSQL quoting 和事务策略需调整 |
| `backend/app/services/core_data_sync.py` | `sync_forecast_facts()` | 使用 MySQL `ON DUPLICATE KEY UPDATE` | PostgreSQL 应改为 `ON CONFLICT DO UPDATE` |
| `backend/app/services/core_data_sync.py` | `save_ai_trace_record()` | 写 `ai_traces`，JSON 以 LONGTEXT 保存 | PostgreSQL 应改为 JSONB 字段 |

### 3.3 AI 助手与聊天记忆

| 文件 | 依赖点 | 说明 | PostgreSQL 迁移风险 |
|---|---|---|---|
| `backend/app/ai/chat_memory.py` | 多处 `apply_database_migrations()` 和 SQL 写入/读取 | 保存 `ai_chat_sessions`、`ai_chat_messages` 等 | 应由 ai_trace/chat repository 管理；证据字段使用 JSONB |
| `backend/app/ai_assistant/memory/conversation_state.py` | 写/读 `ai_conversation_state` | 多轮会话状态落库 | JSON 状态应转 JSONB |
| `backend/app/ai_assistant/service.py` | 调用 `save_ai_trace_record()` | AI Trace 主链路 | PostgreSQL 表结构应明确 trace_id、tools、evidence、guard_result 为 JSONB |
| `backend/app/ai_assistant/tools/tariff_tools.py` | 通过工具读取电价规则表/CSV | 当前工具可查 CSV 和数据库资产 | 正式接口应优先 PostgreSQL，CSV 仅 fallback |
| `backend/app/ai_assistant/tools/knowledge_tools.py` | 文件检索知识库 | 当前未发现 pgvector/embedding | 任务08再接 `kb_documents`、`kb_chunks`、可选 pgvector |

### 3.4 模型运维与预测追踪

| 文件 | 依赖点 | 说明 | PostgreSQL 迁移风险 |
|---|---|---|---|
| `model_ops/active_model_loader.py` | 查 `model_registry` 的 active 模型 | 使用 MySQL engine 和 SQL 文本 | 应迁移到 `model_repo.py` |
| `model_ops/model_registry.py` | 注册模型产物 | 写 `model_registry` | JSON/指标字段应转 JSONB，Active 切换需审计 |
| `model_ops/prediction_tracker.py` | 写 `prediction_tracking` | 预测结果追踪与真实值回填 | PostgreSQL 主事实源关键表 |
| `model_ops/actuals_updater.py` | 更新真实值和误差 | 动态表检查、字段选择、更新误差 | SQL 方言和 repository 边界需治理 |
| `model_ops/error_memory.py` | 构建误差记忆 | 读 `prediction_tracking`、写 `model_error_memory` | JSON/分桶字段迁移，性能需加索引 |
| `model_ops/model_monitor.py` | 读取近期/基线误差 | 判断是否重训 | 应统一通过 model repository |
| `model_ops/model_comparator.py` | 比较 Candidate 和 Active | 写模型对比结果 | Candidate→Active 工作流后续产品化 |
| `model_ops/promotion_manager.py` | 切换 Active 模型 | 更新 `model_registry` | 必须增加审计日志和权限校验 |
| `model_ops/retrain_scheduler.py` | 创建重训任务 | 写 `model_retrain_jobs` | 任务07后应走 Celery |
| `model_ops/strategy_memory.py` | 策略记忆 | 写/读 `model_strategy_memory` | PostgreSQL JSONB 适配 |
| `model_ops/auto_retrain_policy.py` | 检查退化策略 | 读数据库性能表 | 需迁移到 repository |

### 3.5 旧版 GUI / PySide 服务

| 文件 | 依赖点 | 说明 | PostgreSQL 迁移风险 |
|---|---|---|---|
| `ui/services/db_service.py` | 使用 `create_database_engine()` | GUI 数据库浏览 | 后续如果 GUI 保留，需要共用新 db/session |
| `ui/services/forecast_result_service.py` | 使用 MySQL engine 读取预测结果 | GUI 预测结果展示 | PostgreSQL 切换后需适配 |
| `ui/services/model_service.py` | 使用 MySQL engine 读取模型状态 | GUI 模型中心 | 与 Web 模型中心一致迁移 |
| `ui/services/report_service.py` | 使用 MySQL engine 读取报告 | GUI 报告中心 | 与 Web 报告中心一致迁移 |
| `ui/services/legacy_actions.py` | 执行 migrations | 旧 GUI 操作入口 | 应保留兼容或降级 |
| `ui/main_window.py`、`ui/pages/dashboard_page.py` | 显示/测试 MySQL 连接 | 文案和连接状态依赖 MySQL | 后续文案改为 PostgreSQL/DATABASE_URL |

### 3.6 测试与文档

| 文件 | 当前状态 | 迁移影响 |
|---|---|---|
| `tests/test_migrations.py` | 验证 `migrations/*.sql` 幂等和 SQL split | Alembic 引入后需要新增 PostgreSQL migration 测试，旧测试可保留用于 MySQL 兼容 |
| `tests/test_web_platform.py` | 依赖后端接口 shape | 任务06切 PostgreSQL 后必须回归 |
| `tests/test_ai_assistant*.py` | 验证 AI 工具和 Trace 形态 | 任务08必须保证 trace_id、tools、evidence 不退化 |
| `tests/test_model_ops_stage3.py` | 验证预测追踪、误差、监控、候选对比 | PostgreSQL 迁移后重点回归 |
| `README_*.md`、`migrations/README.md` | 仍描述 MySQL、DB_PASSWORD、旧 migrations | 后续阶段更新为 PostgreSQL + Alembic |

## 4. MySQL 专用 SQL/DDL 风险

| 类型 | 当前示例位置 | PostgreSQL 替代方向 |
|---|---|---|
| 连接协议 | `database_utils.py` 的 `mysql+pymysql://` | `postgresql+psycopg://` 或 `postgresql+psycopg2://`，统一走 `DATABASE_URL` |
| 建库语法 | `CREATE DATABASE IF NOT EXISTS ... CHARACTER SET ... COLLATE ...` | 建库交给部署脚本/运维；应用只连接既有库 |
| 标识符 | 反引号 `` `table` `` | SQLAlchemy 模型/表达式，或双引号 `"table"` |
| upsert | `ON DUPLICATE KEY UPDATE` | `ON CONFLICT (...) DO UPDATE` |
| 自增主键 | `AUTO_INCREMENT` | `BIGSERIAL` 或 SQLAlchemy `Identity` |
| 布尔/小整型 | `TINYINT` | `BOOLEAN` 或 `SMALLINT` |
| 长文本 JSON | `LONGTEXT` 保存 JSON 字符串 | `JSONB` |
| 时间字段 | `DATETIME` | `TIMESTAMP WITHOUT TIME ZONE` 或明确带时区策略 |
| 表结构迁移 | 手写 `migrations/*.sql` + `schema_migrations` | Alembic `versions/*.py` |
| 信息架构 | `DATABASE()`、`GROUP_CONCAT ... SEPARATOR` | `current_database()`/`current_schema()`、`string_agg()`、SQLAlchemy inspector |

## 5. 目标后端分层影响

方案要求后端按 `api/schemas/services/repositories/db/workers/ai/ml/core` 分层整理。当前状态与缺口如下：

| 目标层 | 当前已有 | 缺口 |
|---|---|---|
| `api/v1/endpoints` | 已有 system/data/forecast/strategy/assistant/report/model/task | endpoint 仍直接调用部分业务函数，缺少统一 response |
| `schemas` | 当前集中在 `backend/app/schemas.py` | 需拆为 `schemas/forecast.py`、`schemas/assistant.py` 等 |
| `services` | 已有 `backend/app/platform_services.py`、`backend/app/services/core_data_sync.py`、根目录 `services/*.py` | 服务边界仍混合数据访问与业务编排 |
| `repositories` | 当前未发现标准 repository 目录 | 任务04新增，封装 forecast/model/task/ai_trace/report/tariff/user |
| `db` | 当前未发现 `backend/app/db/session.py` | 任务02新增 SQLAlchemy engine/session/get_db |
| `workers` | 当前未发现 Celery worker | 任务07新增 Celery + Redis |
| `ai` | 已有 `backend/app/ai` 和 `backend/app/ai_assistant` | 需要统一工具证据、Trace、RAG、Guard 边界 |
| `ml` | 当前为 `prediction_engine` 和 `model_ops` | 后续可逐步迁移或建立适配层，不宜第一阶段大搬迁 |
| `core` | 当前有 `backend/app/config.py` | 需要新增 `core/config.py`、response、logging、errors、security |

## 6. 第一阶段建议实施边界

根据方案“第一阶段先完成可稳定运行的 PostgreSQL 主库迁移，不要一次性引入过多复杂组件”，建议执行顺序如下：

1. 保留现有 MySQL/Excel 路径，不破坏当前可运行功能。
2. 新增 `backend/app/core/config.py`，只增加统一配置读取，不替换所有调用。
3. 新增 `backend/app/db/session.py`，支持 `DATABASE_URL` 创建 PostgreSQL engine/session。
4. 增加 `psycopg` 或 `psycopg2-binary` 与 `alembic` 依赖。
5. 初始化 Alembic，并创建 PostgreSQL 基线 migration。
6. 第一批 PostgreSQL 表优先覆盖：
   - `forecast_runs`
   - `forecast_results`
   - `model_versions`
   - `model_metrics`
   - `task_logs` 或新 `task_runs` + `task_logs`
   - `ai_traces`
   - `report_runs` / `report_reviews`
   - `pv_tariff_rules`
   - `pv_policy_files`
   - `pv_station_tariff_check`
   - `market_power_price_rules`
   - `southern_grid_tax_rules`
   - `pv_tariff_period_rules`
7. JSON 证据字段使用 JSONB：
   - `ai_traces.tools_json`
   - `ai_traces.evidence_json`
   - `ai_traces.guard_result_json`
   - `ai_traces.trace_json`
   - `forecast_runs.summary_json`
   - `model_versions.metrics_json`
   - `model_metrics.metrics_json`
   - `report_runs.metadata_json`
   - 电价规则表 `raw_json`
8. 暂不引入 Celery/Redis，等任务07执行；本阶段只记录影响。

## 7. 后续任务验收关注点

| 阶段 | 验收重点 |
|---|---|
| 任务02 | 后端可通过 `DATABASE_URL=postgresql+psycopg://...` 创建 engine；`/api/health` 不依赖 MySQL |
| 任务03 | 空 PostgreSQL 库 `alembic upgrade head` 成功；所有核心表存在；JSONB 字段类型正确 |
| 任务04 | `data_access.py`、`platform_services.py` 逐步改为 repository；接口测试通过 |
| 任务05 | MySQL 到 PostgreSQL 迁移脚本输出行数校验和抽样校验报告 |
| 任务06 | 首页、预测中心、模型中心、任务中心、AI助手优先读 PostgreSQL，Excel 仅 fallback |
| 任务07 | 预测、报告、模型训练、知识库索引走 Celery + Redis，不阻塞 FastAPI |
| 任务08 | AI 回答必须保存 trace_id、工具调用、证据来源、Guard 结果；知识库最小 RAG 可用 |
| 任务09 | Docker Compose 可启动 backend、worker、scheduler、postgres、redis、nginx |
| 任务10 | pytest、npm build、冒烟测试通过，输出交付清单 |

## 8. 本阶段未修改内容

本阶段未修改任何业务代码、配置、依赖或数据库结构，仅新增本清单文件。

未执行：

- 未添加 `DATABASE_URL`。
- 未添加 PostgreSQL 驱动。
- 未初始化 Alembic。
- 未修改 `database_utils.py`。
- 未改造 API、service、repository。
- 未引入 Celery/Redis。
- 未迁移真实数据。

原因：根据执行方案，任务01明确要求“禁止修改业务逻辑，只做扫描和清单”。
