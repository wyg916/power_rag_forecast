# P4 任务中心生产化改造报告

生成时间：2026-06-19 19:35（Asia/Shanghai）

## 1. Git 信息

- 当前分支：`p4-task-center-productionization`
- 基线提交：`4bd2d88 docs: add P2 P3 integration readiness report`
- P4 本地提交：`2a4e315 feat: productionize task center runtime`；本报告随后随同一 feature commit amend 更新，最终 HEAD 以 `git log -1 --oneline` 和最终回复为准。
- 是否推送：失败，未触碰 main，未强推。
- 推送失败记录：
  - 第一次：`Recv failure: Connection was reset`
  - 第二次：`Failed to connect to github.com port 443 after 21097 ms: Could not connect to server`
- 是否触碰 main：否。
- 是否进入 P5：否。

## 2. 改造摘要

本轮仅做任务中心生产化增强，不修改 P1 SQL 安全策略，不开放写 SQL，不修改 P2 预测模型/feature schema/backtest 逻辑，不修改 P3 RAG 业务逻辑。

主要改造：

- 新增 `backend/app/services/task_runtime.py`，统一任务状态、任务类型别名、队列映射、超时/重试默认策略、payload hash 和 idempotency key 生成。
- 增强 `backend/app/workers/dispatcher.py`，任务入队时写入生命周期字段、幂等字段、队列名、超时和重试策略；Celery 使用分层队列投递。
- 增强 `backend/app/workers/tasks.py`，命令型任务支持轮询取消与超时；Python handler 任务支持执行前后取消/超时检查、错误编码和结构化步骤日志。
- 增强 `backend/app/repositories/task_repository.py`，支持 task_runs/task_logs 新字段、日志分页、幂等查询和 runtime health 汇总。
- 增强 `backend/app/api/v1/endpoints/task.py`，补齐 `/api/tasks/health`、`GET /api/tasks/{task_id}/logs`、`POST /api/tasks/{task_id}/cancel`、`POST /api/tasks/{task_id}/retry`。
- 增强前端任务中心页面，展示 execution mode、队列状态、任务生命周期字段、日志分页、取消/重试操作和失败处理建议。
- 更新 Docker Compose Celery worker 队列：`default,rag,embedding,report,forecast,data_sync,celery`。

## 3. 数据库 migration 摘要

新增 migration：

- `migrations/versions/0007_task_runtime_productionization.py`
- Revision ID：`0007_task_runtime`
- Down revision：`0006_auth_users`

新增字段：

- `task_runs`：`queued_at`、`error_code`、`error_detail`、`cancel_reason`、`cancelled_at`、`timeout_seconds`、`timeout_at`、`max_retries`、`parent_task_id`、`original_task_id`、`idempotency_key`、`payload_hash`、`dedupe_window_seconds`、`queue_name`
- `task_logs`：`level`、`step`、`sequence_no`

新增索引：

- `idx_task_runs_queue_name`
- `idx_task_runs_idempotency_key`
- `idx_task_runs_payload_hash`
- `idx_task_runs_parent_task_id`
- `idx_task_runs_timeout_at`
- `idx_task_logs_task_step`
- `idx_task_logs_level`
- `idx_task_logs_created_at`

Docker smoke 首次暴露出 Alembic `version_num VARCHAR(32)` 限制，原 revision id `0007_task_runtime_productionization` 超长；已修正为 `0007_task_runtime`，并新增测试覆盖 revision 长度。

容器内验证：

- `alembic current`：`0007_task_runtime (head)`
- `alembic heads`：`0007_task_runtime (head)`
- `select version_num from alembic_version;`：`0007_task_runtime`

## 4. 任务生命周期状态图

```text
pending -> queued -> running -> success
                         |-> failed
                         |-> timeout
                         |-> cancel_requested -> cancelled
pending/queued -> cancelled
failed/cancelled/timeout -> retrying/new child task -> pending
```

统一状态集合：

- `pending`
- `queued`
- `running`
- `success`
- `failed`
- `cancelled`
- `timeout`
- `retrying`
- `cancel_requested`

兼容映射：

- `ok` / `done` / `completed` -> `success`
- `error` / `exception` -> `failed`
- `cancelling` -> `cancel_requested`

## 5. 幂等策略

新增字段：

- `idempotency_key`
- `payload_hash`
- `dedupe_window_seconds`

规则：

- 显式传入 `idempotency_key` 时优先使用。
- 未显式传入时，按 `task_type + business_key + payload_hash[:16]` 生成。
- `payload_hash` 忽略运行期字段：`created_by`、`retry_of`、`retry_count`、`parent_task_id`、`original_task_id`、`force_new`、`dedupe_window_seconds`、`idempotency_key`。
- 对 `pending`、`queued`、`running`、`retrying`、`cancel_requested` 中的同类任务做窗口内去重。
- retry 会携带 `force_new=True`，避免被幂等机制错误合并。

任务业务 key：

- `knowledge_import`：路径/根路径/source_path/limit_files。
- `embedding_refresh`：scope/doc_id/source。
- `report_generate`：report_id/run_id/report_type。
- `data_sync`/`sync_core_data`：source/start/end/date/market。
- `forecast_run`/`fast_forecast`：model_version/start/end/date/market/mode。

## 6. 超时与重试策略

默认策略：

| 任务类型 | timeout_seconds | max_retries | queue |
| --- | ---: | ---: | --- |
| knowledge_import | 1800 | 2 | rag |
| embedding_refresh | 3600 | 2 | embedding |
| report_generate/report_only | 600 | 2 | report |
| data_sync/sync_core_data/refresh_data | 1800 | 3 | data_sync |
| forecast_run/fast_forecast/today_analysis | 1800 | 2 | forecast |
| retrain_model/model_auto_optimize | 3600 | 1 | forecast |
| health_check | 300 | 1 | default |

实现情况：

- 任务记录写入 `timeout_seconds` 和 `timeout_at`。
- 命令型任务使用 `Popen` 轮询，超时后 terminate/kill，并标记 `timeout`。
- Python handler 任务记录超时策略，并在执行前后检查取消和超时。
- retry 只允许 `failed`、`cancelled`、`timeout`，拒绝 active 状态。
- 超过 `max_retries` 后返回 400。
- retry 创建新任务并记录 `parent_task_id/original_task_id/retry_of`，保留原任务失败日志。

## 7. 取消机制

实现情况：

- `POST /api/tasks/{task_id}/cancel` 对 pending/queued 任务直接标记 `cancelled`。
- running 任务设置 `cancel_requested=true`、`cancel_reason`，并尝试 Celery revoke。
- worker 不只依赖 revoke：命令型任务轮询 `cancel_requested`，检查到后安全终止并标记 `cancelled`。
- Python handler 任务执行前后检查 `cancel_requested`；handler 内部的硬中断仍依赖后续细分任务支持。
- 取消原因写入结构化日志。

Docker smoke 验证：

- 手工写入 pending 验收任务 `task_p4_smoke_cancel`。
- 调用 `POST /api/tasks/task_p4_smoke_cancel/cancel` 返回 `cancelled`。
- 详情显示 `cancel_requested=true`、`cancel_reason=p4 smoke pending cancel`、`cancelled_at` 已写入。

## 8. 日志分页

接口：

- `GET /api/tasks/{task_id}/logs?page=1&page_size=50`

实现：

- `page >= 1`
- `1 <= page_size <= 200`
- 返回 `total/items/text`
- 日志字段包含 `level`、`step`、`message`、`metadata`、`sequence_no`
- 步骤建议值：`prepare`、`validate`、`execute`、`persist`、`cleanup`

Docker smoke 验证：

- `GET /api/tasks/task_697d85871275/logs?page=1&page_size=20` 返回 4 条以上步骤日志。
- `task_p4_smoke_failed` 原失败任务 retry 后保留 `retry created: task_f01570a3b653` 日志。

## 9. 队列分层

队列映射：

- `default`
- `rag`
- `embedding`
- `report`
- `forecast`
- `data_sync`

Docker Compose：

- Celery worker 启动参数已加入 `-Q default,rag,embedding,report,forecast,data_sync,celery`。

`/api/tasks/health` 返回：

- `execution_mode`
- `redis.ok`
- `celery.ok`
- `celery_available`
- `active_workers`
- `queue_summary`
- `status_counts`
- `running_task_count`
- `pending_task_count`
- `failed_task_count`
- `timeout_task_count`

Docker smoke health 摘要：

- `execution_mode=celery`
- `redis.ok=true`
- `celery.ok=true`
- `queue_summary` 包含 `default` 和 `embedding`
- `status_counts` 包含 `cancelled=1`、`failed=1`、`success=3`

## 10. 前端改造

改动文件：

- `frontend/src/api.ts`
- `frontend/src/services/taskApi.ts`
- `frontend/src/pages/task/TaskCenterPage.tsx`

新增展示：

- 任务类型、状态、进度、队列、创建/开始/完成时间、retry_count、execution_mode。
- payload 摘要、result_ref、error_message、timeout_seconds、worker_id、celery_task_id。
- 运行健康：execution_mode、redis/celery 状态、worker/queue 汇总。
- 日志分页入口、取消、重试、详情。
- failed/cancelled/timeout 分别展示处理建议。

构建结果：

- `cd frontend && npm run build`：通过。

## 11. 测试结果

编译：

- `python -m py_compile backend/app/api/v1/endpoints/task.py backend/app/repositories/task_repository.py backend/app/workers/dispatcher.py backend/app/workers/tasks.py backend/app/services/task_runtime.py migrations/versions/0007_task_runtime_productionization.py`：通过。

P4 专项：

- `python -m pytest tests/test_p4_task_lifecycle.py tests/test_p4_task_idempotency.py tests/test_p4_task_retry_cancel_timeout.py tests/test_p4_task_logs.py tests/test_p4_task_health.py -q --durations=20`
- 结果：`13 passed`

P1 回归：

- `python -m pytest tests/test_data_trust_service.py tests/test_ai_database_table_freshness.py -q --durations=20`
- 结果：`11 passed`

P3 回归：

- `python -m pytest tests/test_p3_rag_docker_consistency.py -q --durations=20`
- 结果：`4 passed`

既有任务回归：

- `python -m pytest tests/test_task_dispatcher.py tests/test_task_api.py tests/test_task_repository.py -q --durations=20`
- 结果：`9 passed`

前端：

- `npm run build`
- 结果：通过。

## 12. Docker smoke 结果

P3 smoke 容器：

- 项目：`power-trading-ai-p3`
- 状态：保留运行。
- 未删除 volume。

P4 smoke 容器：

- 项目：`power-trading-ai-p4`
- 端口：backend `8010`，frontend `8090`，postgres `5434`，redis `6381`
- 状态：保留运行，便于人工复核。
- 未删除 volume。

容器状态：

- postgres：healthy
- redis：healthy
- backend：healthy
- frontend：healthy
- celery_worker：Up

接口验证：

- `GET http://127.0.0.1:8010/health`：`ok=true`
- `GET http://127.0.0.1:8010/api/tasks/health`：`ok=true`，redis/celery 正常
- `POST /api/tasks` 创建 `health_check`：成功，返回 task_id
- `GET /api/tasks/{task_id}`：成功，包含 lifecycle/queue/timeout 字段
- `GET /api/tasks/{task_id}/logs?page=1&page_size=20`：成功，返回分页步骤日志
- `POST /api/tasks/task_p4_smoke_cancel/cancel`：成功，pending 任务变为 `cancelled`
- `POST /api/tasks/task_p4_smoke_failed/retry`：成功，创建新任务 `task_f01570a3b653`
- retry 新任务最终状态：`success`

RAG/BGE 兼容性观察：

- Docker embedding refresh smoke 显示 `embedding_provider=sentence_transformers`
- `embedding_dim=1024`
- `fallback_enabled=false`
- BGE embedding/reranker model path 均存在且可读

## 13. 已知问题

- Python handler 类型长任务目前在 handler 执行前后检查取消和超时，handler 内部如果进入长时间阻塞，仍需要后续把 handler 拆为可检查步骤；命令型任务已经具备轮询取消/超时。
- `/api/tasks/health` 的 `active_workers` 当前来自运行中任务的 `worker_id` 汇总，不是 Celery inspect 的实时 worker 列表；无运行任务时可能为空，但 redis/celery 状态可用。
- local_thread 模式下记录 `queue_name`，但没有真实多队列隔离；生产建议使用 Celery。
- Docker smoke 中 legacy 输出路径在 JSON 中仍可能显示历史中文路径编码问题，这是既有路径命名问题，不影响 P4 任务中心机制。
- P4 smoke 为避免影响 P3 容器，使用了独立 Compose 项目和独立端口；后续合并前需按目标部署端口重新验收。

## 14. 是否建议进入 P5

建议进入 P5 的前提已满足：

- P4 分支已完成任务生命周期、幂等、超时、重试、取消、日志分页、队列分层、worker health 和前端任务中心增强。
- P1/P3 回归通过。
- P4 Docker smoke 通过，Alembic 已升级到 `0007_task_runtime (head)`。
- 未触碰 main，未强推 main，未删除 volume。

结论：可以进入 P5，但建议进入 P5 前先确认是否保留或停止当前 P3/P4 smoke 容器。
