# P3 RAG / 知识库 / Docker 一致性验收报告

生成时间：2026-06-13 15:00 Asia/Shanghai

## 1. Git 信息

- 当前分支：`p3-rag-docker-consistency`
- 基线 commit：`9699066b4581a2188efeae680b6b7a8fca42beb8`
- 本轮范围：RAG health、Docker BGE 挂载、知识库导入失败分类、embedding refresh warning、前端知识库页状态展示、P3 单测与验收报告。
- 未修改范围：未修改 P1 SQL 安全拦截逻辑；未修改预测模型逻辑；未开放写 SQL；未提交模型权重。

## 2. Docker Compose 改造与配置验收

- `docker version`：Docker Desktop 4.29.0，Engine 26.0.0。
- `docker compose version`：v2.26.1-desktop.1。
- `docker compose --env-file .env.docker.example config --quiet`：通过。
- `docker-compose.yml` 已对 `backend` 和 `celery_worker` 显式挂载：
  - `${BGE_EMBEDDING_MODEL_HOST_PATH:-./bge-large-zh-v1.5}:${RAG_EMBEDDING_MODEL_PATH:-/app/models/bge-large-zh-v1.5}:ro`
  - `${BGE_RERANK_MODEL_HOST_PATH:-./bge-reranker-v2-m3}:${RAG_RERANK_MODEL_PATH:-/app/models/bge-reranker-v2-m3}:ro`
- `.env.docker.example` 已新增 BGE 配置：
  - `RAG_EMBEDDING_PROVIDER=sentence_transformers`
  - `RAG_EMBEDDING_MODEL_PATH=/app/models/bge-large-zh-v1.5`
  - `RAG_EMBEDDING_DIM=1024`
  - `RAG_RERANK_PROVIDER=bge`
  - `RAG_RERANK_MODEL_PATH=/app/models/bge-reranker-v2-m3`

说明：默认项目名 `power-trading-ai` 本机已有旧同名容器占用，未删除旧容器；本次 smoke 使用独立项目名 `power-trading-ai-p3` 启动。

## 3. 容器运行态验收

启动命令：

```powershell
docker compose --env-file .env.docker -p power-trading-ai-p3 up -d
```

容器状态：

- `postgres`：healthy，端口 `5433->5432`
- `redis`：healthy，端口 `6380->6379`
- `backend`：healthy，端口 `8000->8000`
- `celery_worker`：running
- `frontend`：healthy，端口 `8080->80`

基础接口：

- `GET /health`：`ok=true`
- `GET /api/db/health`：`ok=true`，PostgreSQL 主库连接正常
- `GET /api/tasks/health`：`ok=true`，`execution_mode=celery`，`celery_available=true`
- 前端 `http://127.0.0.1:8080`：HTTP 200
- Alembic：`0006_auth_users (head)`

容器内模型挂载：

- `/app/models/bge-large-zh-v1.5`：存在且可读，包含 `config.json`、`pytorch_model.bin`、`tokenizer.json` 等真实模型文件。
- `/app/models/bge-reranker-v2-m3`：存在且可读，包含 `config.json`、`model.safetensors`、`tokenizer.json` 等真实模型文件。

## 4. RAG Health 结果

新增接口：

- `GET /api/knowledge/health`

鉴权：

- 新 smoke 数据库未内置 `wyg_admin`，使用仓库既有 `scripts/create_admin_user.py` 在临时 P3 容器数据库创建验收账号后通过登录。
- `POST /api/auth/login`：通过。
- `GET /api/auth/me`：通过，角色 `admin`。

RAG health 关键字段：

```json
{
  "status": "normal",
  "embedding_provider": "sentence_transformers",
  "embedding_model_path": "/app/models/bge-large-zh-v1.5",
  "embedding_model_path_exists": true,
  "embedding_dim": 1024,
  "rerank_provider": "bge",
  "rerank_model_path": "/app/models/bge-reranker-v2-m3",
  "rerank_model_path_exists": true,
  "kb_document_count": 33,
  "kb_chunk_count": 36,
  "embedded_chunk_count": 36,
  "fallback_enabled": false,
  "fallback_reasons": [],
  "embedding_dim_distribution": {
    "1024": 36
  }
}
```

结论：容器内未发生 embedding/rerank fallback，BGE large zh 维度为 1024，chunk 与 embedding 数量一致。

## 5. 知识库导入与 Embedding Refresh

知识库导入：

- 入口：`POST /api/knowledge/index-local`
- 任务 ID：`task_66b62f4d7a22`
- 执行模式：Celery
- 状态：success
- 耗时：约 484.817 秒
- 结果：
  - `indexed_documents=33`
  - `documents=33`
  - `chunks=36`
  - `failed=[]`
  - `failure_summary={}`

Embedding refresh：

- 入口：`POST /api/knowledge/embedding-refresh`
- 任务 ID：`task_5f2c6bc95759`
- 状态：success
- 耗时：约 0.625 秒
- `warnings=[]`
- refresh 后 health：
  - `embedded_chunk_count=36`
  - `embedding_dim_distribution={"1024":36}`
  - `fallback_enabled=false`

降级处理：

- 新增逻辑会在 refresh 前后检查 RAG health。
- 若 `fallback_enabled=true`，任务 `metadata.result.warnings` 会写入降级原因。
- 单测已覆盖模型路径缺失时 fallback 原因可见、refresh warning 可见。

失败文件分类：

- 知识库导入结果现在包含 `failed[].reason` 和 `failure_summary`。
- 分类包括：
  - `parse_failed`
  - `scanned_pdf_needs_ocr`
  - `unsupported_format`
  - `encoding_exception`

## 6. RAG Search Smoke Test

入口：

- `GET /api/knowledge/search?q=PJM%20LMP%20price%20mechanism&top_k=3`

结果摘要：

- `available=true`
- `item_count=3`
- `evidence_count=3`
- 第一条 evidence：`pjm_lmp_price_mechanism`
- `embedding_provider=sentence_transformers`
- `embedding_dim=1024`
- `embedding_fallback=false`
- `reranker=bge`
- 总耗时：约 `61162 ms`

说明：首次中文 query smoke 因 PowerShell URL 编码显示为乱码，但检索链路本身返回了正确 evidence；报告采用英文 query 作为可读 smoke 记录。

## 7. 前端验收

前端改造：

- `frontend/src/api.ts` 新增 `knowledgeHealth()`。
- `frontend/src/services/knowledgeApi.ts` 聚合 `knowledgeStats + knowledgeHealth`。
- `frontend/src/pages/knowledge/KnowledgeBasePage.tsx` 新增“RAG 运行状态”区域。

页面验收：

- 登录账号：`wyg_admin`
- 页面：`http://127.0.0.1:8080/#/knowledge/knowledge-policy`
- 显示结果：
  - “RAG 运行状态”
  - 状态：`正常`
  - `Embedding 维度：1024`
  - `Chunks：36`
  - `已向量化：36`
  - `Embedding 路径：/app/models/bge-large-zh-v1.5（存在）`
  - `Reranker 路径：/app/models/bge-reranker-v2-m3（存在）`
- 浏览器控制台：无 warning/error。

## 8. 测试结果

Python 编译：

```powershell
python -m py_compile backend/app/services/rag_health_service.py backend/app/services/rag_service.py backend/app/workers/tasks.py backend/app/api/v1/endpoints/knowledge.py
```

结果：通过。

P3 单测：

```powershell
python -m pytest tests/test_p3_rag_docker_consistency.py -q --durations=20
```

结果：`4 passed in 4.65s`。

前端构建：

```powershell
npm run build
```

结果：通过，Vite build completed。

Docker build：

- backend 镜像构建成功。
- frontend 镜像构建成功。
- backend 首次 build 因 `sentence-transformers` 拉取 PyTorch 及 CUDA 相关 wheel，耗时较长。

## 9. 已知问题与风险

1. Docker backend 镜像依赖膨胀：`sentence-transformers` 默认解析到包含 CUDA 依赖的 PyTorch wheel，构建时间很长，镜像体积会显著增加。后续建议评估 CPU-only PyTorch wheel、独立 embedding 服务或预构建基础镜像。
2. BGE 首次真实推理耗时较长：知识库导入首轮约 485 秒，RAG search 首轮 reranker 加载后仍约 61 秒。后续建议增加模型 warmup、批处理参数和 worker 资源配置说明。
3. 新 smoke 数据库不会自动创建 `wyg_admin`，需要在容器启动后执行既有脚本创建验收账号。生产部署应通过安全的初始化流程或密钥管理传入管理员账号。
4. `JWT_SECRET_KEY` 仍使用默认占位符时，容器日志会提示安全风险。生产环境必须替换真实 secret。

## 10. 结论

P3 目标已完成：

- Docker Compose 已显式挂载 BGE embedding 和 reranker 模型目录。
- RAG health 可返回 provider、model path、embedding_dim、chunk_count、embedded_count、fallback 状态和最近刷新时间。
- 容器内知识库导入、embedding refresh、RAG search smoke test 已通过。
- 模型缺失和 refresh fallback warning 已有单测覆盖。
- 前端知识库页面已展示 RAG 当前模式、维度、chunk 数、embedding 数和模型路径。

建议：可以进入下一阶段，但 P4 前建议先处理 Docker 镜像体积和首次推理耗时风险。
