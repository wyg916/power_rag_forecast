# 本地标准运行指南

## 1. 定位与边界

本指南对应当前“可稳定本地运行的企业级开发/演示基线”。它不是生产部署手册，不授权真实业务数据库、生产 Active、正式预测、RAG、报告或策略任务。

所有命令均从项目根目录执行。真实密钥只写入本地 `.env`；仓库仅提交 `.env.example`。

## 2. 前置条件

- Windows 11。
- 项目虚拟环境：`.venv\Scripts\python.exe`。
- Node.js/npm 位于 `PATH`；也可通过 `NODE_HOME`、`NPM_EXE` 指定。
- PostgreSQL 可用，但必须连接开发库或验收隔离库。
- Docker Desktop 使用 Linux Engine；Redis 脚本默认使用 `desktop-linux` 上下文。
- 模型严格推理环境 `.codex_envs\t002_sklearn160` 必须保留。

复制 `.env.example` 为本地 `.env` 后填写开发配置。不得提交 `.env`。

## 3. PostgreSQL

本仓库当前没有经过本阶段验收的“PostgreSQL 单独启动脚本”。请先通过既有本地 PostgreSQL 安装启动服务，再把隔离开发库连接写入 `.env` 的 `DATABASE_URL`。

禁止把正式业务数据库连接串用于本地验收。可使用：

- `intelligent_ops_t001_migration_test`
- `intelligent_ops_t003_transaction_test`
- `intelligent_ops_t005_source_contract_test`
- `intelligent_ops_phase3_acceptance`

以上均为既有验收隔离库，不得自动删除。

## 4. Redis

启动：

```bat
run_redis_local.bat
```

状态检查：

```bat
status_redis_local.bat
```

停止：

```bat
stop_redis_local.bat
```

验收配置为 `redis:7-alpine`，仅发布到 `127.0.0.1:6379`，持久卷停止后保留。

## 5. Celery

先启动 Redis，再启动隔离 health worker：

```bat
run_celery_worker.bat
```

执行联合健康检查：

```bat
run_celery_health.bat
```

停止 worker：

```bat
stop_celery_worker.bat
```

Windows 必须使用 `solo` pool、并发数 `1`，且只监听 `phase4_health`。不得在本指南流程中启动 `default`、`rag`、`embedding`、`report`、`forecast`、`data_sync`、`price_predict` 或 `report_daily` 队列，也不得启动 Celery Beat。

## 6. FastAPI 与前端

仅启动后端：

```bat
run_web_backend.bat
```

仅启动前端：

```bat
run_web_frontend.bat
```

启动或刷新本地 Web 平台：

```bat
run_web_platform.bat
```

后端健康地址：`http://127.0.0.1:8000/api/health`。

前端地址：`http://127.0.0.1:5173`。

## 7. 健康检查

项目健康检查：

```bat
run_health_check.bat
```

Redis/Celery 无副作用健康检查：

```bat
run_celery_health.bat
```

健康检查不得触发 seed、模型激活、正式预测、同步或业务队列。

## 8. 停止顺序

1. 关闭前端和 FastAPI 对应的本地终端或进程。
2. 运行 `stop_celery_worker.bat`。
3. 运行 `stop_redis_local.bat`。
4. 确认应用不再使用隔离 PostgreSQL 后，再按本机 PostgreSQL 管理方式停止服务。

仓库当前没有已验收的 Web 平台一键停止脚本，因此不提供未验证的强制结束命令。

## 9. 重启顺序

1. 确认 PostgreSQL 隔离开发库可连接。
2. `run_redis_local.bat`。
3. `run_celery_worker.bat`。
4. `run_web_platform.bat`。
5. `run_health_check.bat`。
6. `run_celery_health.bat`。

## 10. 常见错误

### Docker Engine 无响应

如果 Docker Desktop 界面存在但 `docker version` 或 `docker info` 超时：

1. 保存当前工作。
2. 由用户手动完全退出 Docker Desktop。
3. 重新启动 Docker Desktop。
4. 等待 Linux Engine ready。
5. 重新执行 `docker version`、`docker info` 和 `run_redis_local.bat`。

不要由项目脚本自动重启 Windows 服务、WSL 或修改系统设置。

### Redis 6379 冲突

先只读检查监听者：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 6379
```

不要自动结束未知进程。确认占用者后，由用户决定停止占用服务或在 `.env` 中调整 `REDIS_PORT`。

### Celery worker 未被发现

- 确认 Redis `PING=PONG`。
- 确认 worker 名为 `phase4-health@<hostname>`。
- 确认队列仅为 `phase4_health`。
- 查看 `output\runtime_logs\phase4\celery_health_worker.log`。

## 11. 日志与临时目录

- Web 日志：`output\runtime_logs\`
- Phase4 日志：`output\runtime_logs\phase4\`
- Phase4 PID/状态：`.codex_tmp\phase4_runtime\`
- Phase4 临时目录：`.codex_tmp\phase4_runtime_tmp\`
- 测试和构建临时资源：`.codex_tmp\`

所有项目缓存、数据库、日志、构建输出和备份必须位于项目盘，不得写入 C 盘。系统软件自身的安装目录和系统日志不属于项目数据。

## 12. 模型与数据隔离

- `.codex_envs\t002_sklearn160` 是已验证的 Python 3.11.9 / sklearn 1.6.0 / LightGBM 4.6.0 推理环境，禁止清理。
- `model_artifacts` 中 joblib 二进制不提交 Git；manifest、schema、metrics、model card、thresholds 和 training config 可作为外部事实元数据提交。
- Candidate 不得自动晋升 Active。
- 本地健康检查不得执行正式预测。

## 13. 当前已知限制

- 训练时 LightGBM 精确版本仍为 `unknown`。
- Docker Desktop 版本较旧，升级不属于本任务。
- 当前运行说明不覆盖 RAG 恢复、AI 100 题、报告/策略闭环或企业生产部署。
- 没有已验收的 PostgreSQL 单独启动脚本和 Web 平台一键停止脚本。
