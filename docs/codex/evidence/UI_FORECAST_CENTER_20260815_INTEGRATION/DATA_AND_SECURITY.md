# API、PostgreSQL 与安全状态

## API / 数据库对账

- 预测中心 16 个必需 GET API：16/16 HTTP 200。
- `/api/forecast/24h`：`run_20260801T140000000000Z_b2a2935315`，24 行。
- API min/max/avg：`24.281544944259206` / `200.9554685490914` / `64.20971584480952`。
- PostgreSQL min/max/avg：`24.281544944259206` / `200.9554685490914` / `64.2097158448095`，与 API 在数值精度范围内一致。
- 只读身份：`beta10d_app_login`，`rolsuper=false`，`transaction_read_only=on`。
- 集成后核对计数：raw_weather=17520、task_runs=20、task_logs=80、forecast_runs=3、forecast_results=48。

## 影响边界

- 数据库迁移：0。
- schema/表/索引变更：0。
- 业务数据写入：0。
- 模型注册、激活或状态切换：0。
- Golden Set、RAG release/alias、production alias：0。
- 后端审计追溯字段继续保留；只从预测中心前端展示中移除了用户指定的过期原因、生成/更新时间、run_id、模型/特征版本、预测日期、区域、推理模型、适用窗口和批次状态。
- 浏览器功能验收额外触发一次真实 `POST /api/forecast/run`。接口返回 200；后台完成态没有被任务中心追踪，因此不把它登记为预测事实已更新。未执行迁移、模型切换或生产配置变更。
