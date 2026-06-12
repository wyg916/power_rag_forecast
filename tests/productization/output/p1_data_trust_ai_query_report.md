# P1 数据可信与 AI 查数能力落地报告

生成日期：2026-06-12  
分支：`p1-data-trust-ai-query`  
阶段范围：建设数据目录、字段映射、数据新鲜度 API、只读 SQL 服务，并让 AI 查数回答说明表名、字段、时间范围、查询摘要和查不到原因。

## 1. 已完成能力

### 1.1 数据目录与字段映射

新增统一服务：

- `backend/app/services/data_trust_service.py`

核心能力：

- 内置 P1 数据目录 `CORE_DATASETS`，覆盖市场电价、日前/实时价格、负荷、天气、建模主表、预测结果、预测误差、模型注册、特征重要性和任务运行记录。
- 每张表登记：
  - `table_name`
  - `display_name`
  - `business_domain`
  - `description`
  - `time_field`
  - `grain`
  - `refresh_frequency`
  - `source_system`
  - `source_url`
  - `fields`
- 字段映射包含：
  - `field_name`
  - `business_name`
  - `meaning`
  - `unit`
  - `role`
  - `runtime_type`

新增 API：

| API | 说明 |
| --- | --- |
| `GET /api/data/catalog` | 返回 P1 数据目录 |
| `GET /api/data/catalog?include_runtime=true` | 返回数据目录并附带运行态建表检查 |
| `GET /api/data/fields` | 返回全部字段映射 |
| `GET /api/data/fields?table=raw_weather` | 返回指定表字段映射 |

### 1.2 数据新鲜度 API

新增 API：

| API | 说明 |
| --- | --- |
| `GET /api/data/freshness` | 按 P1 数据目录批量检查 freshness |
| `GET /api/data/freshness?tables=raw_weather&tables=forecast_results` | 检查指定表 |

返回内容覆盖：

- 表名
- 中文名
- 状态
- 时间字段
- 起始时间
- 最新时间
- 记录数
- 时间字段缺失数
- 查不到原因
- 查询摘要

数据库不可用时，API 不抛 500，而是返回结构化 `available=false` 与 `not_found_reason`。

### 1.3 只读 SQL 服务

新增 API：

```text
POST /api/data/sql/query
```

请求体：

```json
{
  "sql": "SELECT datetime, temperature FROM raw_weather ORDER BY datetime DESC",
  "params": {},
  "limit": 100
}
```

安全边界：

- 只允许单条 `SELECT`。
- 禁止注释，避免隐藏多语句或危险操作。
- 禁止多语句分号。
- 阻断 `insert/update/delete/drop/alter/create/truncate/merge/grant/revoke/copy/call/execute/vacuum/analyze/attach/detach/replace/upsert/set/show/use` 等关键字。
- 只允许访问 P1 数据目录中的业务数据表。
- 默认拒绝 `users`、`audit_logs` 等未纳入 P1 查数目录的敏感/管理表。
- 后端强制外层 `LIMIT`，最大 500 行。
- 参数只接受标量值，并过滤非法参数名。

返回内容覆盖：

- `safe`
- `available`
- `sql`
- `tables`
- `columns`
- `records`
- `row_count`
- `time_range`
- `query_summary`
- `not_found_reason`

### 1.4 AI 查数能力

新增 AI 工具：

- `query_business_data`

新增意图：

- `data_sql_query`

路由规则：

- 包含明确表名并询问“查数、查询、最新几条、多少条、记录数、SQL、SELECT”等时，进入 `data_sql_query`。
- 包含明确表名并询问“新鲜度、更新、截止、到哪天、最新时间、数据范围、最新是几号”等时，继续进入 `database_table_freshness`，保持已有语义不回归。
- 无明确表名但包含“数据库/数据表/查数/最新几条/记录数”与天气、预测结果、负荷、电价、模型误差等业务域时，尝试通过数据目录别名识别表。

AI 回答模板现在固定说明：

- 表名
- 字段
- 时间范围
- 时间字段
- 查询摘要
- 查不到原因
- 结果预览

示例回答结构：

```text
结论：已按只读 SQL 查到 2 条结果预览。

查数口径：
1. 表名：raw_weather
2. 字段：datetime、temperature
3. 时间范围：2026-06-10 00:00:00 至 2026-06-11 00:00:00，时间字段 datetime
4. 查询摘要：查询 raw_weather 最新 2 条记录。

结果预览：
1. datetime=...
```

查不到时会说明：

- 未识别表名
- 表不在 P1 数据目录
- 数据库不可用
- 表不存在
- 查询成功但无匹配记录
- SQL 被安全规则拦截

### 1.5 前端数据中心入口

新增/更新：

- `frontend/src/api.ts`
- `frontend/src/services/dataApi.ts`
- `frontend/src/app/router.tsx`
- `frontend/src/pages/data/DataCenterPage.tsx`

数据中心新增页签：

- `数据目录`

页面展示：

- P1 数据目录表
- 字段映射详情
- 数据新鲜度列表
- 只读 SQL 查数框
- SQL 安全拦截/无结果/成功结果提示

## 2. 测试覆盖

新增测试：

- `tests/test_data_trust_service.py`

覆盖：

- 数据目录无需数据库也可返回。
- 字段映射可返回业务字段。
- SQLite 内存库下 freshness 可计算 `min/max/count`。
- 只读 SQL 可查询目录表。
- 写操作 SQL 被拦截。
- 非目录表如 `users` 被拦截。
- AI 路由可识别 `data_sql_query`。
- AI 工具输出包含表名、字段、时间范围、查询摘要。
- `/api/ai/chat` 端到端调用 `query_business_data`。
- `/api/data/catalog`、`/api/data/fields`、`/api/data/sql/query` API 形状正常。

已执行命令：

```text
python -m pytest tests/test_data_trust_service.py tests/test_ai_database_table_freshness.py -q --durations=20
```

结果：

```text
7 passed in 7.66s
```

```text
python -m py_compile backend\app\services\data_trust_service.py backend\app\api\v1\endpoints\data.py backend\app\ai_assistant\core\intent_router.py backend\app\ai_assistant\service.py backend\app\ai_assistant\templates\deterministic_answers.py backend\app\schemas.py
```

结果：通过。

```text
python -m pytest tests/test_data_trust_service.py tests/test_ai_database_table_freshness.py tests/test_web_platform.py::test_database_table_browser_endpoints_are_safe tests/test_ai_assistant.py::test_ai_assistant_core_intents -q --durations=20
```

结果：

```text
9 passed in 32.55s
```

```text
npm run build
```

结果：

```text
tsc && vite build 通过
```

## 3. 边界与后续建议

本阶段未做：

- 未修改预测模型逻辑。
- 未修改核心预测输出。
- 未开放任意 SQL 或写 SQL。
- 未让 AI 自动生成复杂多表 SQL。
- 未访问 `users`、`audit_logs` 等管理/敏感表。

建议后续：

- P1 后续可以增加基于数据目录的自然语言字段消歧，例如“日前均价”自动映射到 `raw_da_price.da_price`。
- 可以将只读 SQL 服务的 allowlist 配置化，但默认仍应排除认证、审计和系统管理表。
- P2/P3 可把查数结果和 RAG 证据统一进 trace 质量评估。
- P6 部署前应对 SQL 查询增加审计日志和频率限制。
