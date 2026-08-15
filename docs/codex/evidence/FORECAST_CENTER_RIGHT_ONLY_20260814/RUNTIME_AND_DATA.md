# 运行来源与数据链路

## 候选实例

- 鉴权前端：`http://127.0.0.1:5186/#/forecast/24h`，PID `14372`。
- 浏览器验收前端：`http://127.0.0.1:5188/#/forecast/24h`，PID `13164`；仅关闭前端登录门禁，API 仍代理到同一真实 8016 后端并发送 developer 身份。
- 后端：`http://127.0.0.1:8016`，PID `25660`。
- 两个前端命令行均明确指向候选 worktree 的 `frontend/node_modules/.../vite.js`；8016 由候选 worktree 的 `run_project.bat` 启动，启动日志记录同一分支、SHA 与候选日志目录。
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
- 当前 API 明确返回 `is_stale=true`；页面以中性“需复核”状态呈现，不显示“已过期”、过期原因或审计字段，也不把历史结果伪装为当前实时数据。
- `raw_weather`、`task_runs`、`task_logs`、`forecast_runs`、`forecast_results` 验收前后计数一致；业务写入 0。

8016 真实候选实例启用了 Bearer 鉴权，未登录请求返回预期 401，developer 调用预测写接口返回预期 403 且未执行写入。数据一致性使用同一候选代码和同一受控 PostgreSQL 配置的只读 Repository 查询完成，没有读取或输出真实账号口令。
