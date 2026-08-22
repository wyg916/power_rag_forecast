# Startup control evidence

- 独立端口：backend `18000`、frontend `15173`；启动前均空闲。
- `start`：后端、前端、Celery 均健康；backend/frontend 的 command line 包含目标 worktree，可证明来源。
- `status`：展示 branch、SHA、tag、PID、port、working directory、health、log path。
- 日志：集中于 `logs/runtime/20260822_195459/`；后端、前端、Celery、controller 分离。
- `stop`：`stopped=backend,frontend,celery failures=none`，退出码 0。
- 最终状态：18000/15173 无监听 PID，Celery stopped，无孤儿。
- 正式端口：8000/5173 已有来源不能精确证明的进程；控制器拒绝覆盖或终止。
- 默认可见控制台：1；`--silent` 入口使用隐藏窗口，设计值 0。
