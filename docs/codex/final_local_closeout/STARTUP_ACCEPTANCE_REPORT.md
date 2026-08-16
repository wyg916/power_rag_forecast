# 一键启动验收报告

结论：`STARTUP_ROUND_1=PASS`，`STARTUP_ROUND_2=PASS`，最终 `STOPPED_CLEANLY`。

## 冷启动轮

从 8000/5173/6379/6333 零监听、三个 worker PID 全部失活、Redis/Qdrant 容器停止开始执行 `run_project.bat`。PostgreSQL 最小权限身份、Alembic、Redis、Qdrant TLS/只读 Key/8,339 点正式集合、健康 worker、预测 worker、Memory worker、FastAPI 完整 RAG 预热、Vite 和组合健康全部 PASS。

首次诊断发现 Qdrant 正式集合冷恢复约 77 秒，旧启动器只等待约 60 秒。提交 `09a2fc9` 将默认重试上限调整为 48 次（约 4 分钟、仍 fail-closed），10 个启动契约测试通过。其后两次完整冷启动均成功。

## 运行态幂等轮

在资源已运行时再次执行 `run_project.bat`：

- Redis、健康 worker、预测 worker、Memory worker 均返回 `idempotent: true`；
- 后端/前端识别为 already healthy；
- Web PID 22196/22436、worker PID 20744/11396/23872、Redis/Qdrant 容器 ID 重跑前后全部不变；
- 无端口冲突、无重复进程，组合健康任务成功。

## 最终停机

仅针对本候选实例执行受控 worker、Web、Redis 和 Qdrant stop。最终四端口零监听、三个 worker 活跃 PID 为 0、两个项目容器均停止且卷保留；未影响其他 Docker 项目。
