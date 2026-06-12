# P0.1 收尾验收报告

生成日期：2026-06-12  
项目路径：`E:\智能运营分析项目`  
阶段边界：本轮只做 P0.1 基线冻结、Docker 运行态验收、pytest 超时定位与报告沉淀；未进入 P1 业务功能改造，未修改核心业务逻辑、预测模型逻辑或 AI 回答链路。

## 1. Git 仓库状态

| 项目 | 结果 |
| --- | --- |
| 当前目录 | `E:\智能运营分析项目` |
| 当前分支 | `p0-baseline-local` |
| remote | `origin https://github.com/wyg916/power_rag_forecast.git` |
| baseline commit | `8ed7fb0827ad422e633c41e84b6570bd20dcd48b` |
| baseline commit message | `chore: freeze P0 baseline after productization validation` |
| baseline tag | `p0-baseline-20260612` |
| 是否已推送远程 | 是，`p0-baseline-local` 分支和 `p0-baseline-20260612` tag 均已推送 |
| 远程分支状态 | 远程当前仅发现 `origin/p0-baseline-local`，未发现 `origin/main` 或 `origin/master` |
| main 覆盖风险 | 未推送、未强推、未覆盖 main |

执行摘要：

```text
git init
git remote add origin https://github.com/wyg916/power_rag_forecast.git
git checkout -b p0-baseline-local
git add .
git commit -m "chore: freeze P0 baseline after productization validation"
git tag p0-baseline-20260612
git push -u origin p0-baseline-local
git push origin p0-baseline-20260612
```

补充处理：

- 项目最初不是 Git 仓库，上级目录也未发现 Git 仓库，因此按 P0 要求初始化本地仓库。
- 为避免提交本地运行产物、模型大文件、虚拟环境、日志、临时 Office 文件和知识库中间产物，已补充 `.gitignore`。
- 第一次远程探测曾受网络连接影响失败；后续 push 成功，且 `git fetch origin --prune`、`git ls-remote --heads origin` 已验证远程分支。

## 2. Docker Compose 运行态验收结果

### 2.1 Docker 版本

```text
Docker Client Version: 26.0.0
Docker Server: Docker Desktop 4.29.0 (145265), Engine 26.0.0
Docker Compose version v2.26.1-desktop.1
```

### 2.2 Compose 配置与启动

| 检查项 | 结果 |
| --- | --- |
| `docker compose --env-file .env.docker config --quiet` | 通过 |
| `docker compose --env-file .env.docker up -d --build` | 通过 |
| frontend 实际访问端口 | `http://127.0.0.1:8080` |
| 验收后关闭 | 已执行 `docker compose --env-file .env.docker down` |

### 2.3 容器状态

验收时 `docker compose ps`：

| 服务 | 状态 | 端口/说明 |
| --- | --- | --- |
| postgres | Up, healthy | `5433 -> 5432` |
| redis | Up, healthy | `6380 -> 6379` |
| backend | Up, healthy | `8000 -> 8000` |
| celery_worker | Up | 正常启动并连接 Redis；compose 未配置 healthcheck |
| frontend | Up, healthy | `8080 -> 80` |

### 2.4 后端与前端健康

| 接口/命令 | 结果 |
| --- | --- |
| `GET http://127.0.0.1:8000/health` | 200，`{"ok":true,"platform":"售电交易 AI 辅助决策平台","version":"v2.11.2"}` |
| `GET http://127.0.0.1:8000/api/db/health` | 200，`{"ok":true,"active":"postgresql","message":"PostgreSQL 主库连接正常。"}` |
| `GET http://127.0.0.1:8000/api/tasks/health` | 200，`{"ok":true,"execution_mode":"celery","celery_available":true,"message":"ok"}` |
| `HEAD http://127.0.0.1:8080/` | 200 |
| `docker compose exec backend alembic current` | `0006_auth_users (head)` |

### 2.5 登录、用户管理与任务中心

| 检查项 | 结果 |
| --- | --- |
| 正式账号 `wyg_admin` 登录 | 200，返回 JWT |
| `/api/auth/me` | 200，`auth_mode=jwt`，`role=admin` |
| `/api/users?page=1&page_size=5` | 200，`users_total=2` |
| 任务中心 health | 200，`execution_mode=celery`，`celery_available=true` |
| `tests/productization/check_task_center_runtime.py` | 通过 |
| `tests/productization/check_postgres_runtime.py` | 通过 |

说明：

- 容器数据库初始只有 `dev_admin`，未包含正式账号 `wyg_admin`；已使用项目自带 `scripts/create_admin_user.py` 在容器数据库中初始化正式管理员账号。
- 该操作只初始化容器运行态账号，未修改业务代码。

### 2.6 AI/RAG 与 BGE 挂载检查

| 检查项 | 结果 |
| --- | --- |
| AI capability smoke | 200，回答可用，耗时约 20.8 秒 |
| RAG/LMP smoke | 200，回答可用，耗时约 5.8-11.2 秒 |
| 容器 RAG 检索 | `available=true`，返回 2 条，知识库统计 `documents=33`、`chunks=36` |
| 容器 embedding provider | `local_hash` |
| 容器 embedding model | `local-hash-bge-small-zh-v1.5-compatible` |
| embedding dim | 256 |
| embedding fallback | `false` |
| reranker | `local_heuristic` |
| BGE embedding/reranker 真实挂载 | 未通过 |

容器环境变量显示：

```text
RAG_ENABLED=1
RAG_PROFILE=balanced
RAG_EMBEDDING_PROVIDER=local
RAG_EMBEDDING_MODEL=local-hash-bge-small-zh-v1.5-compatible
RAG_EMBEDDING_MODEL_PATH=
RAG_EMBEDDING_MODEL_NAME=
RAG_EMBEDDING_FALLBACK_PROVIDER=hash
RAG_EMBEDDING_DEVICE=cpu
```

结论：

- AI/RAG 在容器环境中可用，能完成检索和回答。
- 当前容器没有真实挂载 BGE embedding/reranker 模型路径；实际为 256 维 local hash embedding 与 local heuristic reranker。
- 这不是 Docker Compose 启动失败，但属于 RAG 质量与生产化风险，应在 P3/P6 或正式部署前补齐模型卷挂载与配置校验。

其他风险：

- backend/celery 日志提示 `JWT_SECRET_KEY uses a default placeholder while auth is enabled or production mode is active.`，上线前必须替换为强随机密钥。
- celery worker 以 root 身份运行有安全警告，生产部署前建议调整容器用户。

## 3. pytest 超时定位结果

### 3.1 用户指定目录命令结果

当前项目测试不是 `tests/api`、`tests/services`、`tests/unit` 的目录结构，而是 `tests/test_*.py` 扁平结构。

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/api -q --durations=20` | 目录不存在，no tests ran |
| `python -m pytest tests/services -q --durations=20` | 目录不存在，no tests ran |
| `python -m pytest tests/productization -q --durations=20` | 无 pytest 用例，no tests ran |
| `python -m pytest tests/unit -q --durations=20` | 目录不存在，no tests ran |

### 3.2 按文件族拆分结果

| 分组 | 命令摘要 | 结果 | 主要慢项 |
| --- | --- | --- | --- |
| 认证/用户/审计 | `test_auth*.py`、`test_user*.py`、`test_audit_logs.py` | 27 passed / 47.42s | 用户角色/密码重置类接口用例，单项约 2.7-4.0s |
| 任务/Celery | `test_task*.py`、`test_celery_task_status.py` | 11 passed / 19.53s | `test_create_task_endpoint_returns_task_id` 约 4.58s |
| Web/前端契约 | `test_web_platform.py`、`test_frontend*.py`、`test_assistant_copy_contract.py` | 13 passed / 88.55s | dashboard/scheduled tasks/stage2/model gateway 等接口，单项约 4.7-19.2s |
| 模型/数据 | `test_model*.py`、`test_formal_forecast.py`、`test_leakage_filter.py`、`test_data_standardization.py`、`test_fetch_power_market_data_postgres_sync.py` | 12 passed / 17.15s | `LeakageFilterTests::test_build_feature_list_excludes_unavailable_current_hour_fields` 约 8.30s |
| AI | `test_ai*.py` | 41 passed / 222.49s | `test_stage1_acceptance_questions_are_answerable` 约 50.60s；`test_ai_assistant_core_intents` 约 46.17s；多条 AI/RAG/Stage2 用例 6-16s |
| RAG/Tariff | `test_rag_hybrid.py`、`test_tariff_ai_tools.py` | 8 passed / 35.00s | tariff 工具调用、policy/evidence 检索，单项约 4.9-9.0s |
| 迁移/安全/启动脚本 | `test_migrations.py`、`test_secret_masking.py`、`test_stage1_safety.py`、`test_startup_scripts.py`、`test_deepseek_config_security.py` | 12 passed / 15.24s | bat 文件格式/迁移 SQL 幂等检查，单项约 1.3-4.0s |

### 3.3 完整 pytest 复跑结果

```text
python -m pytest -q --durations=20
124 passed in 289.86s (0:04:49)
```

180 秒超时原因：

- 不是测试失败或死锁。
- 完整测试集可通过，但当前全量运行约 290 秒，超过 180 秒超时上限。
- 最大耗时集中在 AI assistant、RAG/知识检索、Web 平台聚合接口和少量数据扫描类用例。

全量 Top 慢项摘要：

| 用例 | 耗时 | 分类判断 |
| --- | ---: | --- |
| `tests/test_ai_assistant.py::test_stage1_acceptance_questions_are_answerable` | 46.71s | AI/RAG 多问题验收，偏 slow/integration/rag |
| `tests/test_ai_assistant.py::test_ai_assistant_core_intents` | 28.81s | AI 意图与回答链路验收，偏 slow/integration |
| `tests/test_web_platform.py::test_model_gateway_health_and_chat_feedback` | 13.76s | Web/模型网关集成 |
| `tests/test_web_platform.py::test_scheduled_tasks_endpoint_is_safe` | 13.45s | Web/任务接口集成 |
| `tests/test_ai_answer_no_evidence_leak.py::test_default_chat_answer_hides_debug_and_evidence_paths` | 13.23s | AI 回答安全契约 |
| `tests/test_ai_assistant.py::test_ai_assistant_hour_explain_uses_hour_tool` | 11.91s | AI 工具链 |
| `tests/test_ai_assistant.py::test_followup_reason_uses_previous_low_price_context` | 9.81s | AI 上下文追问 |
| `tests/test_ai_assistant.py::test_ai_assistant_forecast_extreme_is_question_specific` | 9.35s | AI/预测解释集成 |
| `tests/test_ai_assistant.py::test_weather_question_answers_weather_not_power_price` | 8.61s | AI 工具路由 |
| `tests/test_leakage_filter.py::LeakageFilterTests::test_build_feature_list_excludes_unavailable_current_hour_fields` | 7.37s | 数据字段扫描/规则校验 |

### 3.4 慢测试归因

| 类型 | 是否存在 | 说明 |
| --- | --- | --- |
| 真实 LLM 调用 | 未发现全量测试必须依赖真实外部 LLM；当前更像本地/模拟 AI 链路验收 |
| RAG embedding/rerank 重模型调用 | 存在 RAG/检索链路，但当前容器配置不是 BGE 重模型；本地测试耗时主要来自检索、工具链和多问题串行验收 |
| Docker/Celery 集成测试 | 存在任务中心/Celery 语义测试，但不是最大耗时来源 |
| 外部 API 调用 | 未定位到必须依赖外部 API 的失败点 |
| 数据库长查询 | Web 平台聚合接口和数据浏览接口有集成查询耗时，应继续监控 |
| 测试等待超时或 mock 不完整 | AI/Web 集成用例存在串行调用过多、mock 粒度偏粗的问题，是 180s 超时的主因 |

### 3.5 quick/full test 建议

建议 quick test 用于提交前快速回归，覆盖认证、用户管理、任务中心、核心模型和少量 RAG/Web smoke：

```powershell
$quick = @(
  'tests/test_auth_login.py',
  'tests/test_auth_jwt.py',
  'tests/test_auth_permissions.py',
  'tests/test_auth_rbac.py',
  'tests/test_user_management_api.py',
  'tests/test_task_api.py',
  'tests/test_task_dispatcher.py',
  'tests/test_celery_task_status.py',
  'tests/test_model_artifacts.py',
  'tests/test_formal_forecast.py',
  'tests/test_rag_hybrid.py',
  'tests/test_web_platform.py::test_health_endpoint_returns_platform_metadata',
  'tests/test_web_platform.py::test_task_center_health_endpoint'
)
python -m pytest $quick -q --durations=20
```

建议 full test 用于阶段验收/CI：

```powershell
python -m pytest -q --durations=20
```

CI 超时建议：

- quick test：建议 180 秒。
- full test：建议至少 600 秒，当前基线实测约 290 秒，预留冷启动和机器性能波动后建议 8-10 分钟。

### 3.6 marker 处理建议

本轮已在 `pytest.ini` 补充 marker 定义：

- `slow`
- `integration`
- `docker`
- `llm`
- `rag`

本轮未批量修改现有测试用例标签，避免在 P0.1 阶段大范围触碰测试文件。建议 P1 开始前或 P1 首个测试治理提交中：

- 将 `tests/test_ai_assistant.py::test_stage1_acceptance_questions_are_answerable`、`tests/test_ai_assistant.py::test_ai_assistant_core_intents` 标记为 `slow`、`integration`、`rag`。
- 将 RAG/knowledge evidence 类用例标记为 `rag`。
- 将 Docker Compose 依赖的验收脚本或未来 pytest 用例标记为 `docker`、`integration`。
- 将真正访问外部 LLM 的用例标记为 `llm`，并默认从 quick test 中排除。
- 对 AI 多问题验收拆分 smoke/full：quick 保留 1-2 个代表性问题，full 保留完整验收集。
- 对 model gateway、scheduled tasks、数据库表浏览等 Web 聚合接口增加 mock 或 fixture 缩小数据面。

## 4. 是否可以进入 P1

结论：可以进入 P1 数据可信与 AI 查数能力改造。

判断依据：

- Git baseline 已冻结：`p0-baseline-local` 分支、`8ed7fb0827ad422e633c41e84b6570bd20dcd48b` baseline commit、`p0-baseline-20260612` tag 均已完成并推送。
- Docker Compose 已完成运行态验收：postgres、redis、backend、frontend、celery worker 均可启动；健康接口、迁移版本、登录、用户管理、任务中心均通过。
- pytest 慢用例已定位：完整测试可通过，180 秒超时原因明确为全量耗时约 290 秒，核心慢项集中在 AI/RAG/Web 集成式测试。

进入 P1 前保留风险：

- BGE embedding/reranker 未真实挂载，当前为 local hash embedding 与 local heuristic reranker。该风险不阻塞 P1 数据可信与 AI 查数能力改造，但应作为 P3 RAG 质量增强或 P6 部署前置项处理。
- Docker 环境中 `JWT_SECRET_KEY` 使用默认占位值的警告必须在上线前处理。
- full test 建议调整 CI 超时到 600 秒以上，或先完成 slow/integration/rag marker 分层后再收紧 quick test。
