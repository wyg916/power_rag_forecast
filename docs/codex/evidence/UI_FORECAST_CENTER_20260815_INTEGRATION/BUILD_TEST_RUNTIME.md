# 构建、测试、启动与最终运行实例来源

## 最终 Release 自动门禁

| 项目 | 结果 |
|---|---|
| `git diff --check` | PASS |
| TypeScript `tsc --noEmit` | PASS |
| `npm run build` | PASS，3675 modules transformed |
| 预测中心、七态与相关回归 | 27 passed；7 个需要项目隔离数据库 runner 的用例按既有 guard 拦截，由真实 API/只读 PostgreSQL 对账补充，不修改或降低 guard |
| 跨页面页头契约 | PASS，包含最新数据中心、报告中心和预测中心路径 |
| `run_project.bat` 集成内容提交第一次 | PASS，SHA `a3135a67…`，5200/8040，统一健康检查成功，退出码 0 |
| `run_project.bat` 集成内容提交第二次 | PASS，SHA `a3135a67…`，幂等复用 5200/8040，统一健康检查成功，退出码 0 |

直接运行数据库上下文测试且不使用项目隔离数据库 runner 时，pytest 会按既有 guard 主动清理数据库配置并拒绝执行。该门禁保持不变；业务验收使用现行真实服务和只读 PostgreSQL 身份完成。

## 进程来源

| 用途 | URL/端口 | PID | 工作目录/命令来源 |
|---|---|---:|---|
| 最终前端 | `http://127.0.0.1:5190` | 23780 | `E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807\frontend` |
| 最终后端 | `http://127.0.0.1:8030` | 19288 | 最终路径中运行 `uvicorn backend.app.main:app` |

运行分支：`release/beta10d-agent-rc-20260807`。运行实例的命令行、PID 和工作目录均指向用户指定的真正最终路径，不复用旧 worktree 进程。
