# Docker Compose 企业部署说明

本部署包用于将 AI 售电交易决策平台以容器方式运行，包含 PostgreSQL、Redis、FastAPI 后端、Celery Worker、前端静态服务与 `/api` 反向代理。

## 文件清单

| 文件 | 作用 |
|---|---|
| `docker-compose.enterprise.yml` | 企业部署编排，包含 postgres、redis、backend、worker、frontend |
| `.env.docker.example` | Docker 环境变量样例，不包含真实密码 |
| `docker/Dockerfile.backend` | 后端镜像，启动前自动等待 PostgreSQL 并执行 Alembic migration |
| `docker/Dockerfile.frontend` | 前端镜像，Vite 构建后由轻量 Node 静态服务提供页面 |
| `docker/frontend-server.mjs` | 前端 SPA 路由和 `/api` 反向代理 |
| `scripts/docker_compose_smoke_test.ps1` | 企业栈构建、启动和冒烟测试脚本 |
| `run_docker_enterprise.bat` | Windows 一键 Docker 企业部署入口 |

## 一键冒烟测试

```powershell
.\run_docker_enterprise.bat
```

默认使用以下本机端口，避免和本地开发环境冲突：

| 服务 | 地址 |
|---|---|
| 前端 | `http://127.0.0.1:18080` |
| 后端 | `http://127.0.0.1:18000` |
| PostgreSQL | `127.0.0.1:15432` |
| Redis | `127.0.0.1:16379` |

冒烟测试会检查：

1. Docker Compose 配置有效性。
2. 后端 `/api/health`。
3. 前端 `/health`。
4. 前端静态服务 `/api` 反向代理。
5. 数据质量、系统健康、策略配置接口。
6. Alembic 当前版本。
7. Celery Worker 可创建。

## 正式部署

复制环境变量样例并修改密码：

```powershell
Copy-Item .env.docker.example .env.docker
```

启动：

```powershell
docker compose --env-file .env.docker -f docker-compose.enterprise.yml up -d --build
```

查看状态：

```powershell
docker compose --env-file .env.docker -f docker-compose.enterprise.yml ps
```

停止容器但保留数据卷：

```powershell
docker compose --env-file .env.docker -f docker-compose.enterprise.yml down
```

## 注意事项

- PostgreSQL 是主事实源，后端容器启动前会执行 `alembic upgrade head`。
- Redis 用于 Celery 异步任务。
- Ollama/qwen3 不是容器栈的硬依赖；不可用时 AI 助手会进入工具证据优先的降级链路。
- 不要把 `.env.docker`、真实客户数据、API Key、模型大文件提交到代码仓库。
