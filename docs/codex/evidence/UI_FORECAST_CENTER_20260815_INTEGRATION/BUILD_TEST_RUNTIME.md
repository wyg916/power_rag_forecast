# 构建、测试、启动与运行实例来源

## 最新 Release 再收敛后的自动门禁

| 项目 | 结果 |
|---|---|
| `git diff --check` | PASS |
| TypeScript `tsc --noEmit` | PASS |
| `npm run build` | PASS，3675 modules transformed，54.20s |
| 预测中心与七态契约测试 | 22 passed，3 个 DB 上下文用例按项目 guard deselected，并由真实 API/只读 PostgreSQL 对账替代 |
| 跨页面页头契约 | PASS，包含最新数据中心、报告中心和预测中心路径 |
| `run_project.bat` 第一次 | PASS，SHA `e1c3e324…`，启动默认 8000/5173，统一健康检查成功，退出码 0 |
| `run_project.bat` 第二次 | PASS，SHA `e1c3e324…`，幂等复用默认服务，统一健康检查成功，退出码 0 |

直接运行包含数据库上下文的测试组且不加载获批本地数据库配置时得到 7 项环境失败；没有修改或降低测试。预测中心 3 项由项目 guard 隔离，数据中心 4 项属于最新 Release 自身的受控数据库上下文，业务验收使用现行服务和只读身份完成。

## 进程来源

| 用途 | URL/端口 | PID | 工作目录/命令来源 |
|---|---|---:|---|
| 一键启动前端 | `http://127.0.0.1:5173` | 20656 | `E:\智能运营分析项目_worktrees\integrate_forecast_center_20260815\frontend` |
| 一键启动后端 | `http://127.0.0.1:8000` | 22584 | integration worktree 中运行 `uvicorn backend.app.main:app` |
| 视觉验收前端 | `http://127.0.0.1:5188` | 23204 | integration worktree `frontend`；仅关闭前端认证门禁用于三页可视化验收 |
| 视觉验收后端 | `http://127.0.0.1:8016` | 23064 | integration worktree 中运行 `uvicorn backend.app.main:app` |

运行分支：`codex/integrate-forecast-center-20260815`。一键启动日志明确打印 SHA `e1c3e324d4c5a4bfd410c30d842cf6561a7dafea`；本目录所在提交只增加验收文档与图片。
