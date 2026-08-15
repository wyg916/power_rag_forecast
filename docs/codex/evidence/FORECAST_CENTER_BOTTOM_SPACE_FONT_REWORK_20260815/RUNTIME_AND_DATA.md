# 运行实例与真实数据链路

## 候选实例来源

| 端口 | PID | 用途 | 来源证明 |
|---|---:|---|---|
| 8016 | 25468 | 真实后端 | 候选 `run_project.bat` 启动；`uvicorn backend.app.main:app --port 8016` |
| 5186 | 25400 | 一键启动前端 | 命令行明确指向候选 worktree 的 `frontend/node_modules/.../vite.js` |
| 5188 | 24180 | 浏览器视觉验收前端 | 工作目录为候选 `frontend`，Vite 代理目标为 8016 |

- 候选分支：`codex/ui-forecast-center-fidelity-20260814`
- 本轮源代码提交：`91644ca`
- 候选工作目录：`E:\智能运营分析项目_worktrees\ui_forecast_center_fidelity_20260814`
- 候选地址：`http://127.0.0.1:5188/#/forecast/24h`

## API / PostgreSQL 对账

- 数据库：`localhost:5432/postgres`。
- 运行角色：`beta10d_app_login`，查询事务显式 `READ ONLY`。
- API 与数据库最新 `run_id` 均为 `run_20260801T140000000000Z_b2a2935315`。
- API 与数据库记录数均为 24。
- min / max / avg 均逐项一致：`24.281544944259206` / `200.9554685490914` / `64.2097158448095`。
- 预测中心依赖的 16 个 GET API 全部 HTTP 200。
- GET 前后保护表计数一致：`raw_weather=17520`、`task_runs=19`、`task_logs=77`、`forecast_runs=3`、`forecast_results=48`；业务写入 0。
- 无数据库迁移、Seed、模型反序列化、模型激活、RAG 发布或生产切换。
