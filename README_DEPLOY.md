# 智能运营分析项目 Docker Compose 部署说明

本文档用于本地服务器或演示环境的一键部署。所有密钥只允许写入本机 `.env.docker` 或企业密钥管理系统，不要提交到代码仓库。

## 1. 环境要求

- 本地后端：Python `3.11.x`
- 本地前端：Node.js `>=18 <25`、npm `>=9 <12`
- Docker Engine 24+ 或 Docker Desktop
- Docker Compose v2
- Compose 示例端口：`5433`、`6380`、`8000`、`8080`；启动前先检查冲突
- 服务器可访问外部大模型 API 时，按需配置 DeepSeek/OpenAI 等 Key
- 如使用本地 Ollama，可在宿主机启动 Ollama，或用 compose 的 `ollama` profile 启动

## 2. 准备环境变量

复制示例文件：

```bash
cp .env.docker.example .env.docker
```

必须检查并修改：

```env
POSTGRES_PASSWORD=<本机随机强密码>
JWT_SECRET_KEY=<至少32字符的随机密钥>
AUTH_REQUIRED=1
ADMIN_INITIALIZED=1
DATABASE_ALLOW_LEGACY_FALLBACK=0
TASK_EXECUTION_MODE=celery
CORS_ALLOWED_ORIGINS=http://your-frontend-domain
```

`.env.docker.example` 中的 `replace_with_*` 只是可解析占位值，后端会拒绝把它当作生产密钥。可在本机执行
`python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成随机值；不得把结果写入 Git、日志或验收报告。

首次管理员初始化应分两步执行：先仅启动 PostgreSQL/Redis，使用本机 `.env.docker` 中的
`ADMIN_USERNAME`、`ADMIN_PASSWORD` 运行 `python scripts/create_admin_user.py`，确认成功后再设置
`ADMIN_INITIALIZED=1` 并启动完整服务。该标记不得在管理员尚未创建时虚假开启。

如使用 DeepSeek：

```env
LLM_PROVIDER=deepseek
MODEL_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
```

不要把真实 `DEEPSEEK_API_KEY`、数据库密码或任何 Authorization token 写入 README、测试、日志或代码。
默认示例将外部 LLM 与 RAG 设为禁用，未配置时健康状态必须显示 disabled/unavailable，不得伪报可用。
启用前需显式设置 `AI_ASSISTANT_LLM_ENABLED=1` 或 `RAG_ENABLED=1`，并验证模型路径、维度和服务健康。

## 3. 启动服务

先做只读配置解析：

```bash
python scripts/day2_repro_preflight.py --env-file .env.docker.example
docker compose --env-file .env.docker config
docker compose -f docker-compose.enterprise.yml --env-file .env.docker config
```

确认占位密钥已在未跟踪的 `.env.docker` 中替换、管理员已受控初始化、端口无冲突后再启动：

```bash
docker compose --env-file .env.docker up -d --build
```

默认服务：

- `postgres`：PostgreSQL 主事实源
- `redis`：Celery broker/result backend
- `backend`：FastAPI 后端
- `celery_worker`：知识库导入、embedding 刷新、报告生成等异步任务
- `frontend`：前端静态服务和 `/api` 反向代理

可选启动 Ollama：

```bash
docker compose --env-file .env.docker --profile ollama up -d --build
```

## 4. 初始化数据库

默认 `backend` 容器启动时会执行：

```bash
alembic upgrade head
```

生产或活动业务 Schema 禁止直接做验收 downgrade。迁移回放必须使用独立临时 Schema、独立
`alembic_version` 和受限 `search_path`；Day 2 隔离验证使用的环境变量如下：

```env
ALEMBIC_TARGET_SCHEMA=beta10d_day2_<timestamp>
ALEMBIC_SCHEMA_PREFIX=beta10d_day2_
ALEMBIC_EXECUTION_ROLE=beta10d_day2_<timestamp>_role
ALEMBIC_EXPECTED_HOST=localhost
ALEMBIC_EXPECTED_PORT=5432
ALEMBIC_EXPECTED_DATABASE=postgres
ALEMBIC_EXPECTED_USER=postgres
```

隔离 Schema/角色必须由获授权操作员预先创建，回放完成并核对 `public` 与业务指纹后才可精确清理。

如需手动执行：

```bash
docker compose --env-file .env.docker exec backend sh scripts/run_migrations.sh
```

或：

```bash
docker compose --env-file .env.docker exec backend sh scripts/init_db.sh
```

## 5. 导入知识库

如果已有标准 chunk 文件：

```text
knowledge_pipeline/output/chunks.jsonl
```

执行：

```bash
docker compose --env-file .env.docker exec backend sh scripts/import_knowledge.sh
```

默认参数：

- `KNOWLEDGE_CHUNKS_PATH=knowledge_pipeline/output/chunks.jsonl`
- `KNOWLEDGE_IMPORT_MODE=append`
- `KNOWLEDGE_IMPORT_BATCH_SIZE=32`

如使用 BGE embedding，请确保容器能访问模型路径，并在 `.env.docker` 中配置对应 `RAG_EMBEDDING_*` 变量。不要把宿主机绝对路径写进 compose 文件，建议用相对挂载或镜像构建参数统一管理。

## 6. 查看服务状态与日志

```bash
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f backend
docker compose --env-file .env.docker logs -f celery_worker
docker compose --env-file .env.docker logs -f frontend
```

## 7. 健康检查

后端：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/db/health
curl http://127.0.0.1:8000/api/tasks/health
```

前端：

```bash
curl http://127.0.0.1:8080/health
```

容器内统一检查：

```bash
docker compose --env-file .env.docker exec backend sh scripts/health_check.sh
```

`/api/model-gateway/health` 在启用鉴权时需要具备 `model:read` 权限的请求头或企业登录网关。

## 8. 运行测试

本地代码测试：

```bash
python -m compileall backend tests knowledge_pipeline scripts migrations
python -m pytest
cd frontend && npm ci && npm run build
```

容器配置校验：

```bash
docker compose --env-file .env.docker config
```

## 9. 常见问题排查

### Postgres 连接失败

- 检查 `POSTGRES_PASSWORD` 是否与 `.env.docker` 一致。
- 执行 `docker compose --env-file .env.docker logs postgres`。
- 执行 `docker compose --env-file .env.docker exec backend sh scripts/init_db.sh`。

### Redis 连接失败

- 执行 `docker compose --env-file .env.docker logs redis`。
- 检查 `REDIS_URL=redis://redis:6379/0` 是否被改错。
- 如果 `TASK_EXECUTION_MODE=celery`，Redis 不可用会导致任务创建失败，这是生产安全策略。

### DeepSeek 不可用

- 检查 `DEEPSEEK_API_KEY` 是否只在 `.env.docker` 或密钥系统中配置。
- 检查 `DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。
- 后端会通过 LLMRouter 回退本地模型或模板兜底，但不会输出 API Key。

### Ollama 不可用

- 宿主机 Ollama：确认 `LLM_BASE_URL=http://host.docker.internal:11434` 可访问。
- Compose Ollama：使用 `--profile ollama` 启动，并将 `LLM_BASE_URL=http://ollama:11434`。
- 确认模型已拉取，例如 `qwen3:4b`。

### embedding 维度不一致

- 当前项目 BGE 目标维度为 1024。
- 检查 `RAG_EMBEDDING_PROVIDER`、`RAG_EMBEDDING_MODEL_PATH`、`RAG_EMBEDDING_MODEL_NAME`。
- 不要混用旧 hash embedding 和 BGE embedding。

### RAG 检索为空

- 检查 `kb_documents`、`kb_chunks` 是否有数据。
- 执行 `scripts/import_knowledge.sh` 导入 `chunks.jsonl`。
- 检查 `RAG_ENABLED=1`。

### 前端连不上后端

- 前端容器通过 `BACKEND_URL=http://backend:8000` 代理 `/api`。
- 浏览器访问默认地址：`http://127.0.0.1:8080`。
- 检查 `CORS_ALLOWED_ORIGINS` 是否包含真实前端域名。

## 10. 生产建议

- `AUTH_REQUIRED=1`
- `DATABASE_ALLOW_LEGACY_FALLBACK=0`
- `TASK_EXECUTION_MODE=celery`
- 使用企业密钥管理系统注入 API Key 和数据库密码
- 定期备份 `postgres_data`
- 对外只暴露前端或网关入口，后端、Postgres、Redis 不建议直接暴露公网
