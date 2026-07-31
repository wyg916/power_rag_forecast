# Day 4 数据访问面

## 结论

共登记 27 个 API、客户端、AI、仓库、脚本和测试调用面：12 个保留、11 个替换、4 个禁用。Day 4 前识别出 11 个自由 SQL、动态对象或物理元数据高风险入口；最终业务 API 接收原始 SQL 的入口为 0，客户端可控制数据库对象名、Schema、原始列名、SQL 表达式、JOIN、子查询或函数的入口为 0。

逐项清单见 [DATA_ACCESS_SURFACE.csv](./DATA_ACCESS_SURFACE.csv)。清单覆盖数据预览、对象搜索、导出、AI/NL 查询、后端 `text()`/动态标识符、离线脚本和前端参数传递。

## 单一事实源

- 注册表：`backend/app/data_registry.py`。
- 登记 11 个业务数据集；每项包含稳定 ID、中文说明、实际对象、对象类型、公开字段、类型、排序/过滤能力、分页和导出上限、权限、来源分类、敏感等级、AI 可访问性及消费者。
- 注册表导入时校验 ID/对象/字段唯一性、标识符格式、默认排序、页大小、导出上限和敏感字段 token；非测试启动时还验证对象和字段真实存在。
- API 公开契约不返回 `object_name`、`column_name`、Schema 或内部路径。

| dataset_id | 业务对象 | 公开字段数 | 导出 | AI | 消费者 |
| --- | --- | ---: | --- | --- | --- |
| market_price_history | 市场电价历史 | 7 | 是 | 是 | 数据中心 |
| day_ahead_price | 日前电价 | 4 | 是 | 是 | 数据中心 |
| real_time_price | 实时电价 | 4 | 是 | 是 | 数据中心 |
| actual_load | 实际负荷 | 3 | 是 | 是 | 数据中心 |
| load_history | 负荷历史 | 4 | 是 | 是 | 数据中心 |
| load_forecast | 负荷预测 | 3 | 是 | 是 | 数据中心 |
| weather_observations | 天气观测 | 6 | 是 | 是 | 数据中心 |
| forecast_output | 预测输出 | 11 | 是 | 是 | 数据中心、预测中心、AI 助手 |
| prediction_accuracy | 预测准确性 | 9 | 否 | 是 | 数据中心、模型中心、AI 助手 |
| model_inventory | 模型版本清单 | 11 | 否 | 否 | 数据中心、模型中心 |
| feature_importance | 特征重要性 | 5 | 否 | 是 | 数据中心、模型中心、AI 助手 |

实际对象名只用于本表的受控安全审计，不进入公开 API 响应或前端显示。

## 明确排除

默认拒绝 `users`、`roles`、`permissions`、`user_roles`、`audit_logs`、`system_api_configs`、`system_api_test_logs`、`system_runtime_config`、`task_logs`、`task_runs`、`alembic_version`、PostgreSQL 系统目录，以及包含 password/token/secret/credential/connection/api_key/raw_json/payload_json 等字段的对象。

管理员身份只影响业务权限，不绕过数据集注册表。

## 查询边界

- 行查询由 SQLAlchemy Core 从静态 `Table`/`Column` 映射构造；值均绑定参数。
- 排序方向为 `asc|desc` 枚举；字段必须登记为 sortable/filterable/searchable。
- 最大页大小 100，注册表强制不超过 200；查询超时受服务端限制；导出最多 5000 行且需 `data:export`。
- 未注册数据集、字段或非法方向返回脱敏的 4xx；异常不回显 SQL、数据库路径或结果。
- 旧 SQL 路径保留终止性兼容响应：任何请求体、任何角色均返回 410，函数不读取或记录 SQL，也不创建数据库连接。

## 内部动态查询处置

固定业务仓库的 WHERE 片段只由源码枚举，客户端值使用绑定参数。市场仓库额外使用 11 项精确对象/排序/条件策略；电价 AI 工具使用 5 个固定 SQL 字符串，未知组合在触库前拒绝。通用 `query_dataframe` 只保留为内部固定模板执行器，已与任何接收客户端 SQL 的 API 断开。
