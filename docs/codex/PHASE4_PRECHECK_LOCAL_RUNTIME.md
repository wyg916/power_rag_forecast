# PHASE4-PRECHECK 本地 Redis/Celery 运行说明

## 1. 运行边界

- Redis 复用仓库现有 `docker-compose.yml` 的 `redis:7-alpine` 服务。
- 不安装 Windows Redis/Memurai，不修改 Windows 服务、PATH、注册表或防火墙。
- Celery 仅启动一个 Windows `solo` worker，监听独立 `phase4_health` 队列。
- 此 worker 不监听 `default`、`forecast`、`report`、`data_sync`、`embedding` 等业务队列。
- 不启动 Celery Beat，不自动执行预测、报告、采集、同步、seed、模型训练或模型激活。
- TEMP/TMP 固定为项目内 `.codex_tmp\phase4_runtime_tmp`；PID 和日志也位于项目目录。

## 2. 前置条件

1. 项目 `.venv\Scripts\python.exe` 存在，并已安装 `redis` 与 `celery`。
2. Docker Desktop Linux Engine 可用，默认上下文为 `desktop-linux`。
3. 6379 端口未被非 Redis 进程占用。
4. `.env` 中的 `REDIS_URL`、`CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND` 指向本地 Redis。

脚本不会回退到 C 盘或全局 Python；缺少项目虚拟环境时会直接失败。

## 3. 标准启动与验证

```bat
set NO_PAUSE=1
run_redis_local.bat
status_redis_local.bat
run_celery_worker.bat
run_celery_health.bat
```

`run_redis_local.bat` 只执行 `docker compose up -d redis`。若 Redis 已可 PING，则幂等返回成功。

`run_celery_worker.bat` 后台启动单 worker，并写入：

- PID：`.codex_tmp\phase4_runtime\celery_health_worker.json`
- 日志：`output\runtime_logs\phase4\celery_health_worker.log`

`run_celery_health.bat` 会：

1. Redis PING；
2. 向 `phase4_health` 队列提交 `power_trading.health_check_task`；
3. 等待 `SUCCESS`；
4. 从 Redis result backend 读取结果；
5. 输出可追踪 task id。

## 4. 标准停止

```bat
set NO_PAUSE=1
stop_celery_worker.bat
stop_redis_local.bat
```

- Celery 先广播到精确的 `phase4-health@...` worker，再按检查点 PID 收敛进程。
- Redis 只停止 Compose 的 `redis` 服务，不执行 `docker compose down`，不删除 volume。
- PID 文件和日志保留作审计证据，不自动删除。

## 5. 失败关闭与排障

错误地址验证：

```bat
.venv\Scripts\python.exe -X utf8 scripts\phase4_precheck_runtime.py redis ping --url redis://127.0.0.1:1/0
```

预期返回非零退出码，且输出只显示脱敏 URL。

若 Docker 命令超时：

- 不要安装新的 Redis 服务；
- 不要重启 Docker Desktop 服务或 WSL，除非用户明确确认；
- 先检查 Docker Desktop Linux Engine 状态和 `desktop-linux` 上下文；
- 恢复 Engine 后重新执行启动脚本即可。

## 6. 回滚

- 已有文件从 PHASE4-PRECHECK 修改前检查点恢复。
- 新增脚本只能在用户确认后逐文件删除。
- Redis 数据卷保留；如需删除数据卷属于破坏性操作，必须单独确认。
- 本任务不修改数据库迁移、模型 artifact、Active 状态或预测事实链。
