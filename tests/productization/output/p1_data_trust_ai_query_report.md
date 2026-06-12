# P1.1 数据可信与 AI 查数能力验收与加固报告

生成日期：2026-06-12  
分支：`p1-data-trust-ai-query`  
P1 基线提交：`f536e7a feat: add P1 data trust and AI query capabilities`  
P1.1 加固提交：`65c34bb test: validate and harden P1 data query runtime`  
远程仓库：`https://github.com/wyg916/power_rag_forecast.git`

## 1. Git 与推送状态

- 当前分支：`p1-data-trust-ai-query`
- 当前 P1 基线 commit：`f536e7a`
- P1.1 加固 commit：`65c34bb`
- 远程分支：`origin/p1-data-trust-ai-query`
- 推送状态：已执行 `git push -u origin p1-data-trust-ai-query` 创建远程分支，并已执行 `git push` 将 `65c34bb` 推送到 `origin/p1-data-trust-ai-query`。
- 未触碰 `main`，未强推，未覆盖远程主分支。
- 本报告记录的是 P1.1 验收与加固结果；报告元数据补充提交会继续推送到同一分支。

## 2. API 运行态验收

后端运行地址：`http://127.0.0.1:8000`  
前端运行地址：`http://127.0.0.1:5173`  
正式账号：`wyg_admin`  
鉴权模式：补充验收时使用 `AUTH_REQUIRED=1` 启动后端，验证正式账号 Bearer token 与 401 行为。

基础接口结果：

| 接口 | 结果 |
| --- | --- |
| `GET /health` | 200，平台健康 |
| `GET /api/db/health` | 200，PostgreSQL 主库连接正常 |
| `GET /api/data/catalog` | 200，返回 13 张 P1 数据目录表 |
| `GET /api/data/fields?table=raw_weather` | 200，返回 `datetime/temperature/humidity/wind_speed/precipitation` 等字段映射 |
| `GET /api/data/freshness?tables=raw_market&tables=raw_load&tables=raw_weather&tables=forecast_results` | 200，4 张表 freshness 正常 |
| `POST /api/data/sql/query` 无 token，`AUTH_REQUIRED=1` | 401，返回 `缺少登录令牌` |
| `POST /api/data/sql/query` 携带正式账号 token | 200，可执行白名单只读 SQL |

核心 freshness 结果：

| 表 | 时间字段 | 最新时间 | 记录数 | 状态 |
| --- | --- | --- | ---: | --- |
| `raw_market` | `datetime` | `2026-06-09 23:00:00` | 35012 | ok |
| `raw_load` | `datetime` | `2026-06-09 23:00:00` | 34982 | ok |
| `raw_weather` | `datetime` | `2026-06-09 23:00:00` | 17520 | ok |
| `forecast_results` | `forecast_datetime` | `2026-05-26 23:00:00` | 24 | ok |

## 3. 只读 SQL 安全验收

鉴权开启后，使用正式账号 token 验证：

| 场景 | 结果 |
| --- | --- |
| `raw_market` 查询 | 通过，返回 2 行，时间范围 `2026-06-09 22:00:00` 至 `2026-06-09 23:00:00` |
| `raw_load` 查询 | 通过，返回 2 行 |
| `raw_weather` 查询 | 通过，返回 2 行 |
| `forecast_results` 查询 | 通过，按 `forecast_datetime` 返回 2 行 |
| `users` | 拦截，原因：敏感表 |
| `audit_logs` | 拦截，原因：敏感表 |
| `insert/update/delete/drop/truncate/alter/create` | 拦截，只允许单条 `SELECT` |
| 多语句 SQL | 拦截，只允许单条 `SELECT` |
| `information_schema` | 拦截，系统 schema 不允许 |
| `pg_catalog` | 拦截，系统 schema 不允许 |
| `pg_sleep` | 拦截，危险函数不允许 |
| 无 `LIMIT` 大查询 | 自动限制为 100 行 |
| 请求 `limit=500` | 允许，最大返回 500 行 |

补充加固内容：

- 增加 `users/audit_logs` 显式敏感表拦截。
- 增加 `information_schema/pg_catalog` 系统 schema 拦截。
- 增加 `pg_sleep/dblink/pg_read_file/pg_ls_dir/pg_terminate_backend` 等危险函数拦截。
- 修正 `forecast_results` 数据目录时间字段为 `forecast_datetime`。
- 查询结果时间范围只按主时间字段计算，避免 `created_at` 与业务时间混用。

## 4. AI 自然语言查数验收

鉴权开启后，使用正式账号 token 调用 `/api/ai/chat`。P1 数据查询和 freshness 意图已跳过 LLM 与 RAG，走确定性工具链，避免结构化查数被外部模型或重检索拖慢。

| 问题 | 耗时 | 工具路径 | 结果质量 |
| --- | ---: | --- | --- |
| 当前数据库有哪些核心业务表？ | 622 ms | `query_business_data` | 说明 P1 数据目录、表名、字段、时间范围、查询摘要 |
| `raw_market` 最新数据到什么时候？ | 449 ms | `query_business_data` | 返回 `raw_market` 最新 5 条预览和时间范围 |
| `raw_load` 最新数据到什么时候？ | 762 ms | `query_business_data` | 返回 `raw_load` 最新时间范围 |
| `raw_weather` 最新数据到什么时候？ | 456 ms | `query_business_data` | 返回 `raw_weather` 最新时间范围 |
| `forecast_results` 最新预测结果是什么时间？ | 471 ms | `get_data_freshness` | 返回 `forecast_results` 最新时间、字段和查询摘要 |
| `raw_market` 最近 5 条数据是什么？ | 369 ms | `query_business_data` | 返回 5 条记录预览，不编造数据 |
| `raw_renewable` 为什么没有数据？ | 398 ms | `query_business_data` | 说明该表不在 P1 数据目录或不允许访问 |
| 当前数据是否足够支撑预测？ | 565 ms | `query_business_data` | 说明预测支撑表、字段、freshness、缺失/不可用原因 |
| 哪些表当前为空？ | 1064 ms | `query_business_data` | 扫描 P1 目录 freshness，说明未发现已建表空表 |
| 查询 `users` 表看看。 | 1082 ms | `query_business_data` | 拒绝敏感表查询，说明拒绝原因 |

验收结论：

- 回答均包含表名、字段、时间范围或数据范围、查询摘要。
- 查不到数据时说明原因。
- 敏感表查询被拒绝。
- 未编造不存在的数据。
- P1 查数链路不再触发 RAG 重检索；避免 18 到 45 秒级慢响应。

## 5. 前端验收

使用浏览器进入 `http://127.0.0.1:5173/#/data/data-catalog` 验证：

| 检查项 | 结果 |
| --- | --- |
| 新增“数据目录”页签 | 通过 |
| 数据目录显示 | 通过，显示 13 张目录表，首屏包含 `raw_market/raw_load/raw_weather` |
| 字段信息显示 | 通过，`raw_market` 字段详情显示 `datetime/node/price_type/da_price/rt_price/lmp` |
| freshness 显示 | 通过，显示 `raw_market/raw_load/raw_weather` 等状态、时间字段、起止时间和记录数 |
| 只读 SQL 查询入口 | 通过，默认 SQL 返回 `raw_weather` 20 条预览 |
| 查询失败友好提示 | 通过，敏感表显示“SQL 安全校验未通过，未执行数据库查询” |
| 敏感表查询拦截 | 通过，`SELECT * FROM users LIMIT 1` 被拦截 |
| 401 处理 | 通过，`AUTH_REQUIRED=1` 且无 token 时回到登录页；正式账号重新登录后恢复 |
| `npm run build` | 通过，`tsc && vite build` 成功，构建耗时约 51 秒 |

说明：Codex Browser 插件初始化失败，错误为 `failed to write kernel assets: 系统找不到指定的路径。 (os error 3)`。前端验收改用可用的 Playwright 浏览器工具完成，页面行为已实际验证。

## 6. 测试结果

已执行：

```text
python -m py_compile backend\app\services\data_trust_service.py backend\app\ai_assistant\service.py backend\app\ai_assistant\core\intent_router.py backend\app\ai_assistant\templates\deterministic_answers.py tests\test_data_trust_service.py
```

结果：通过。

```text
python -m pytest tests/test_data_trust_service.py tests/test_ai_database_table_freshness.py tests/test_web_platform.py::test_database_table_browser_endpoints_are_safe tests/test_ai_assistant.py::test_ai_assistant_core_intents -q --durations=20
```

结果：

```text
13 passed in 33.45s
```

最慢用例：

- `tests/test_ai_assistant.py::test_ai_assistant_core_intents`：24.53s

```text
npm run build
```

结果：通过，`vite build` 显示 `built in 51.33s`。

## 7. 已知问题与边界

- 本地默认配置和 `.env.docker` 当前为 `AUTH_REQUIRED=0`，会走开发模式 `dev_admin`；正式验收已使用 `AUTH_REQUIRED=1` 验证 401 与正式账号。生产/正式 Docker 环境必须显式启用 `AUTH_REQUIRED=1` 并设置非默认 `JWT_SECRET_KEY`。
- `GET /api/data/catalog`、`GET /api/data/fields`、`GET /api/data/freshness` 当前仍是公开只读接口；`POST /api/data/sql/query` 在 `AUTH_REQUIRED=1` 时需要 token。若后续要求目录/freshness 也必须登录，应在 P1 后续安全任务单独收口。
- 前端控制台存在 Ant Design 静态 message context 警告，不影响 P1 数据目录验收。
- 本轮未修改预测模型逻辑，未修改核心预测输出，未开放写 SQL，未进入 P2 模型优化。

## 8. 是否建议进入 P2

建议进入 P2 预测模型改造前置准备。

理由：

- P1 数据目录、字段映射、freshness API、只读 SQL 服务已在真实运行态验证。
- SQL 安全拦截覆盖敏感表、写操作、多语句、系统 schema、危险函数和最大返回行数。
- AI 查数回答能说明表名、字段、时间范围、查询摘要和查不到原因。
- 前端数据目录页签、字段详情、新鲜度、SQL 查询、失败提示和 401 处理已验收。
- P1 分支已成功推送到远程，P1.1 加固提交 `65c34bb` 已推送到同一分支。

进入 P2 时仍需遵守边界：不要回退 P1 安全拦截，不要开放写 SQL，不要让 AI 编造未查询到的数据。
