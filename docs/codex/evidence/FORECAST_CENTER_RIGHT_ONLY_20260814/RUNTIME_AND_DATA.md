# 运行来源与数据链路

## 候选实例

- 前端：`http://127.0.0.1:5186/#/forecast/24h`，PID `19424`。
- 后端：`http://127.0.0.1:8016`，PID `11920`。
- 前端命令行指向候选 worktree 的 `frontend/node_modules/.../vite.js`。
- 分支：`codex/ui-forecast-center-fidelity-20260814`。
- 工作目录：`E:\智能运营分析项目_worktrees\ui_forecast_center_fidelity_20260814`。

## 真实 API / PostgreSQL 只读核对

- 数据库：`localhost:5432/postgres`。
- 运行角色：`beta10d_app_login`，非超级用户；核对事务显式 `READ ONLY`。
- 预测中心依赖的 16 个 GET API 最终探测全部 HTTP 200，Unexpected 4xx/5xx = 0。
- Unauthorized：未带身份访问预测接口为 401。
- Forbidden：无数据权限身份访问数据质量接口为 403。
- API 与数据库 `run_id` 一致，API 24 个时点 = `forecast_results` 24 行。
- API 与数据库 min/max/avg 逐项一致。
- 当前 API 明确返回 `is_stale=true`，页面通过统一状态契约呈现 Stale，不把历史结果伪装为当前实时数据。
- `raw_weather`、`task_runs`、`task_logs`、`forecast_runs`、`forecast_results` 验收前后计数一致；业务写入 0。

8016 真实候选实例启用了 Bearer 鉴权，未登录 shell 请求返回预期 401。数据一致性使用同一候选代码和同一受控 PostgreSQL 配置的进程内只读 API 上下文完成，没有读取或输出真实账号口令。
