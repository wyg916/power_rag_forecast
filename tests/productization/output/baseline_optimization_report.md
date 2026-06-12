# P0 基线冻结与全链路验收报告

- 生成时间：2026-06-12 20:08:39 +08:00
- 项目路径：`E:\智能运营分析项目`
- 阶段目标：确认当前后端、前端、数据库、Docker、AI/RAG、任务中心、登录和用户管理的真实可运行状态。
- 执行原则：本次仅做基线验收与报告输出，不修改业务逻辑，不写入真实密钥，不读取或记录真实 `.env` 内容。

## 1. 基线环境

| 项目 | 结果 |
|---|---|
| Git 仓库状态 | 当前目录不是 Git 仓库，`git rev-parse --short HEAD` 与 `git status --short` 均失败 |
| 系统 Python | `Python 3.11.0rc2`，路径 `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe` |
| Codex bundled Python | `Python 3.12.13` |
| Node.js | `v24.14.0` |
| npm | `10.2.3` |
| Docker CLI | `Docker version 26.0.0, build 2ae903e` |
| Docker Compose | `Docker Compose version v2.26.1-desktop.1` |
| 前端版本 | `power-trading-ai-platform@2.11.2` |
| Alembic 当前版本 | `0006_auth_users (head)` |

## 2. 脱敏运行配置快照

| 配置项 | 当前值 |
|---|---|
| `APP_ENV` | `development` |
| `AUTH_REQUIRED` | `False` |
| `DATABASE_PRIMARY` | `postgresql` |
| `DATABASE_URL` | 已配置，脱敏后为 `postgresql+psycopg://postgres:***@localhost:5432/postgres` |
| `DATABASE_ALLOW_LEGACY_FALLBACK` | `False` |
| `TASK_EXECUTION_MODE` | `auto` |
| `LLM_PROVIDER` | `deepseek` |
| `LLM_BASE_URL` | `http://localhost:11434` |
| `LLM_MODEL` | `qwen3:4b` |
| `RAG_PROFILE` | `balanced` |
| `JWT_SECRET_KEY` | 当前为默认/占位值 |

说明：当前是开发态验收环境，`AUTH_REQUIRED=False` 会启用本地 dev fallback；生产上线前必须切换为强制认证并替换 JWT secret。

## 3. 验收命令结果

| 类别 | 命令/动作 | 结果 | 摘要 |
|---|---|---|---|
| Git 基线 | `git rev-parse --short HEAD` | 失败 | 当前目录不是 Git 仓库，无法记录 commit |
| Git 工作区 | `git status --short` | 失败 | 当前目录不是 Git 仓库，无法记录脏工作区 |
| Python 编译 | `python -m compileall backend tests knowledge_pipeline scripts` | 通过 | 后端、测试、知识库管道、脚本语法编译通过 |
| Pytest 收集 | `python -m pytest --collect-only -q` | 通过 | 收集到 124 个测试 |
| 完整 Pytest | `python -m pytest -q` | 失败/超时 | 180 秒未完成，命令超时 |
| 前端构建 | `npm run build` | 通过 | TypeScript 与 Vite build 通过，耗时约 1 分 2 秒 |
| Alembic 当前版本 | `alembic current` | 通过 | 当前版本为 `0006_auth_users (head)` |
| Alembic 迁移 | `alembic upgrade head` | 通过 | 无新增迁移需要执行 |
| Docker 配置 | `docker compose --env-file .env.docker config --quiet` | 通过 | Compose 配置可解析 |
| Docker 运行态 | `docker compose --env-file .env.docker ps` | 失败 | Docker daemon 不可连接 |
| Docker 启动 | `docker compose --env-file .env.docker up -d --build` | 失败 | Docker daemon 不可连接 |
| PostgreSQL 脚本 | `python tests/productization/check_postgres_runtime.py` | 跳过 | 直接运行时当前进程未注入 `DATABASE_URL` |
| PostgreSQL 脚本（加载项目配置后） | `python -c "...load_dotenv(); run_path(...)"` | 通过 | 数据库运行态报告通过 |
| 任务中心脚本 | `python tests/productization/check_task_center_runtime.py` | 通过 | 任务状态流转、失败记录、重试、取消检查通过 |
| RAG smoke 脚本 | `python knowledge_pipeline/test_rag_search_after_import.py` | 失败/超时 | 120 秒未完成 |
| RAG 单查询 | `rag_search('LMP 是什么？', top_k=2)` | 通过但慢 | 44.222 秒，BGE 1024 维，未 fallback，返回 2 条 |
| 后端运行态 | `uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` | 通过 | 临时后端启动成功，`/health` 返回 200 |
| 前端运行态 | `npm run dev` | 通过 | 临时 Vite 服务启动成功，`http://127.0.0.1:5173` 返回 200 |

## 4. 后端/API 运行态

| 接口/能力 | 结果 | 说明 |
|---|---|---|
| `/health` | 通过 | 返回 200，平台版本 `v2.11.2` |
| `/api/db/health` | 通过 | 返回 200，`active=postgresql` |
| `/api/tasks/health` | 通过/降级 | 返回 200，`execution_mode=auto`，`celery_available=false` |
| `/api/auth/login` 错误密码 | 通过 | 返回 401 |
| `/api/auth/login` 正式账号 | 通过 | `wyg_admin` 登录成功，返回 JWT，角色 `admin` |
| `/api/auth/me` Bearer token | 通过 | 返回 `auth_mode=jwt`，角色 `admin` |
| `/api/users?page=1&page_size=5` Bearer token | 通过 | 返回 2 个用户 |
| `/api/auth/me` 无 token | 可访问/开发态 fallback | 当前 `AUTH_REQUIRED=False`，返回 `dev_header_fallback` 管理员 |

## 5. 数据库基线

PostgreSQL 运行态检查在加载项目配置后通过：

| 项目 | 结果 |
|---|---|
| 数据库连接 | 通过 |
| Alembic at head | `True` |
| 表数量 | 32 |
| 索引数量 | 28 |
| 核心表 | `forecast_runs`、`forecast_results`、`model_versions`、`model_metrics`、`report_runs`、`report_reviews`、`task_runs`、`task_logs`、`ai_traces`、`audit_logs`、`kb_documents`、`kb_chunks`、`users`、`roles`、`raw_market`、`raw_weather`、`raw_load`、`raw_renewable`、`feature_importance` 均存在 |

已生成的数据库报告：

- `tests/productization/output/postgres_runtime_report.md`
- `tests/productization/output/postgres_runtime_report.json`

## 6. AI/RAG 基线

| 验收项 | 结果 | 摘要 |
|---|---|---|
| AI 能力说明 HTTP smoke | 通过但偏慢 | Python UTF-8 请求返回 200，耗时 26.969 秒，普通模式无 debug 字段 |
| LMP 专业问答 HTTP smoke | 通过 | 返回 200，耗时 6.937 秒，普通模式无 debug 字段 |
| raw_market 新鲜度问答 HTTP smoke | 通过但偏慢 | 返回 200，耗时 37.664 秒，普通模式无 debug 字段 |
| RAG 单查询 | 通过但慢 | `LMP 是什么？` 查询耗时 44.222 秒，`embedding_provider=sentence_transformers`，`embedding_dim=1024`，`embedding_fallback=false`，`reranker=bge` |
| RAG 批量 smoke | 失败/超时 | 10 个默认问题在 120 秒内未完成 |
| AI fast-path 单测 | 通过 | `test_one_sentence_capability_fast_path_no_rag_or_llm` 通过 |

判断：AI/RAG 不是不可用，但当前运行态耗时不稳定。P1/P3 阶段需要重点处理数据查数、RAG health、耗时观测和 Docker 内模型一致性。

## 7. 任务中心基线

`tests/productization/check_task_center_runtime.py` 通过。

| 检查项 | 结果 |
|---|---|
| 创建 pending 任务 | 通过 |
| pending -> running -> success | 通过 |
| failed 任务错误记录 | 通过 |
| retry_count 更新 | 通过 |
| pending 任务取消 | 通过 |
| running 任务取消请求 | 通过 |
| Celery 可用性 | 当前不可用 |
| 执行模式 | `auto` |

已生成任务中心报告：

- `tests/productization/output/task_center_runtime_report.md`
- `tests/productization/output/task_center_runtime_report.json`

## 8. 前端基线

| 验收项 | 结果 | 摘要 |
|---|---|---|
| `npm run build` | 通过 | TypeScript 与 Vite 构建成功 |
| Vite dev server | 通过 | `http://127.0.0.1:5173` 返回 200 |
| 登录页/主页面视觉验收 | 未执行 | P0 本轮只做 HTTP 可访问性，未使用浏览器截图 |

## 9. 专项测试补充

| 测试 | 结果 |
|---|---|
| `tests/test_auth_login.py tests/test_user_management_api.py` | 9 passed |
| `tests/test_task_api.py tests/test_task_repository.py tests/test_task_dispatcher.py` | 9 passed |
| `tests/test_web_platform.py::test_web_health_endpoint tests/test_web_platform.py::test_database_table_browser_endpoints_are_safe` | 2 passed |
| `tests/test_rag_hybrid.py::test_local_embedding_is_nonempty_and_stable` | 1 passed |

## 10. 失败清单与优先级

### P0-blocker

| 问题 | 影响 | 建议 |
|---|---|---|
| 当前目录不是 Git 仓库 | 无法冻结 commit、无法确认工作区是否干净，P0 baseline 不完整 | 将当前项目纳入 Git，或在交付目录中提供 commit/版本标识 |
| Docker daemon 不可连接 | 无法完成最新 Compose 全链路启动、容器健康检查、容器内 RAG/任务/登录验收 | 启动 Docker Desktop/daemon 后重跑 `docker compose --env-file .env.docker up -d --build` |
| 完整 `python -m pytest -q` 180 秒超时 | 后端完整回归未形成通过/失败结论 | 拆分测试集定位慢用例，并设置更明确的 pytest 分层命令 |

### P1-high

| 问题 | 影响 | 建议 |
|---|---|---|
| `AUTH_REQUIRED=False` 开发 fallback 可无 token 访问 admin 能力 | 当前环境不能代表生产认证状态 | P0 生产验收时使用 `AUTH_REQUIRED=1`、非默认 JWT secret 重跑 |
| `JWT_SECRET_KEY` 为默认/占位值 | 不满足上线红线 | 生产环境必须替换为强 secret 或 Secret Manager 注入 |
| `check_postgres_runtime.py` 直接运行会跳过 | 验收脚本依赖 `DATABASE_URL` 注入方式，不利于一键验收 | 统一产品化脚本的配置加载方式，或在脚本文档中明确必须先加载 `.env` |
| RAG 批量 smoke 超时 | AI/RAG 批量验收不可稳定完成 | P3 增加 RAG health、耗时统计、缓存状态、模型加载状态 |
| AI 能力说明与数据新鲜度问答耗时偏高 | 业务用户体验不稳定 | P1/P5 优化 AI 查数 fast-path 和输出结构，避免简单问题进入重链路 |

### P2-medium

| 问题 | 影响 | 建议 |
|---|---|---|
| README/部分中文输出存在编码显示异常 | 影响命令行审查和报告可读性 | 后续统一源文件和脚本输出编码为 UTF-8 |
| Docker Compose 配置可解析但存在疑似乱码路径显示 | 可能影响跨环境挂载一致性 | Docker 运行态恢复后重点检查 volume 是否真实挂载 |
| Celery 当前不可用但 `TASK_EXECUTION_MODE=auto` 返回健康 | 开发态可接受，生产态不能代表长任务稳定性 | P4 用 `TASK_EXECUTION_MODE=celery` 和真实 Redis/Celery 重跑长稳验收 |
| 前端只完成 HTTP 可访问性，未做浏览器截图 | 不能证明页面无白屏、无权限跳转问题 | P5 或 Docker 复验时补 UI smoke 截图 |

## 11. 当前可用能力判断

| 模块 | 判断 |
|---|---|
| 后端 FastAPI | 可用 |
| PostgreSQL 主事实源 | 可用 |
| Alembic 迁移 | 可用，当前在 head |
| 登录/JWT | 可用，`wyg_admin` 正式账号可登录 |
| 用户管理 | 可用 |
| 任务中心 | 开发/数据库状态流转可用，Celery 运行态未验证 |
| 前端构建和本地访问 | 可用 |
| AI/RAG | 可用但耗时不稳定，批量 smoke 未通过 |
| Docker Compose | 配置可解析，但运行态未通过，原因是 Docker daemon 不可连接 |

## 12. 下一步建议

1. 先解决 P0-blocker：恢复 Git 版本标识、启动 Docker daemon、拆分并重跑完整 pytest。
2. 重跑 Docker Compose 最新全链路：backend/frontend/postgres/redis/celery_worker、登录、任务、RAG、前端。
3. 进入 P1 前，优先把 `AUTH_REQUIRED=1`、非默认 JWT secret、`DATABASE_ALLOW_LEGACY_FALLBACK=0` 的验收环境固定下来。
4. P1 优先实现数据目录、新鲜度 API 和只读 SQL 服务，解决 AI 查数可信问题。
5. P3 必须补 RAG health 和容器内 BGE 模型挂载检查，当前 RAG 查询耗时已足够说明需要可观测性。
