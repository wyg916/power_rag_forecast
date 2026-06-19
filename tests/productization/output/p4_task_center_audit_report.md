# P4-0 任务中心生产化现状审计报告

生成时间：2026-06-19 Asia/Shanghai

## 1. Git 信息

- 当前分支：`p4-task-center-productionization`
- 基线来源：`p3-rag-docker-consistency`
- 基线 HEAD：`4bd2d88 docs: add P2 P3 integration readiness report`
- 工作区状态：创建本审计报告前干净
- main 状态：本轮未触碰 main，未强推

## 2. 当前任务表结构

### task_runs

当前已有字段来自 `0001`、`0004`、`0005`：

- 标识：`task_id`、`run_id`、`task_name`、`task_kind`、`task_type`
- 状态：`status`
- 参数：`payload_json`
- 时间：`started_at`、`ended_at`、`finished_at`、`created_at`、`updated_at`
- 运行结果：`duration_seconds`、`error_message`、`progress`、`message`、`result_ref`、`metadata_json`
- 重试与运行态：`retry_count`、`execution_mode`、`cancel_requested`、`worker_id`、`celery_task_id`

缺失字段：

- `queued_at`
- `error_code`
- `error_detail`
- `cancel_reason`
- `cancelled_at`
- `timeout_seconds`
- `timeout_at`
- `max_retries`
- `parent_task_id`
- `original_task_id`
- `idempotency_key`
- `payload_hash`
- `dedupe_window_seconds`
- `queue_name`

### task_logs

当前已有字段：

- `id`、`task_id`、`run_id`、`task_name`、`task_kind`
- `status`
- `command_json`
- `log_path`
- `log_text`
- `started_at`、`ended_at`、`created_at`、`updated_at`
- `duration_seconds`
- `returncode`
- `error_message`
- `progress`
- `message`
- `result_ref`
- `metadata_json`
- `execution_mode`
- `cancel_requested`
- `worker_id`
- `celery_task_id`

缺失字段：

- 结构化日志 `level`
- 结构化步骤 `step`
- `sequence_no`

## 3. 当前任务状态流转

现状状态主要为：

```text
pending -> running -> success
pending -> running -> failed
pending -> cancelled
running -> cancel_requested
```

问题：

- `queued`、`timeout`、`retrying` 未形成统一语义。
- `cancel_requested` 被当作状态使用，但缺少 `cancel_reason/cancelled_at`。
- `retry_count` 已有，但缺少 `max_retries` 和 lineage。
- 失败只有 `error_message`，缺少 `error_code/error_detail`。

## 4. 当前任务创建入口

- `POST /api/tasks/run`
- `POST /api/tasks`
- `POST /api/knowledge/index-local`
- `POST /api/knowledge/embedding-refresh`
- `POST /api/reports/generate`
- `POST /api/reports/{report_id}/regenerate`
- `POST /api/data/refresh`
- `POST /api/data/sync-core`
- `POST /api/forecast/run`

创建逻辑集中在：

- `backend/app/workers/dispatcher.py::enqueue_task`
- `backend/app/task_manager.py::TaskManager.start`

## 5. 当前任务查询、取消、重试入口

- 查询列表：`GET /api/tasks`
- 查询详情：`GET /api/tasks/{task_id}`
- 日志查询：`GET /api/tasks/{task_id}/logs`
- 取消：`POST /api/tasks/{task_id}/cancel`
- 重试：`POST /api/tasks/{task_id}/retry`
- 健康：`GET /api/tasks/health`

问题：

- 日志接口当前偏向整段文本读取，不支持分页、level、step。
- 重试只允许 failed/cancelled，不支持 timeout。
- 重试没有检查 max_retries。
- 取消主要依赖 repository 状态和 Celery revoke，worker 侧缺少统一检查函数。

## 6. 当前执行模式

执行模式：

- `TASK_EXECUTION_MODE=celery`
- `TASK_EXECUTION_MODE=local_thread`
- `TASK_EXECUTION_MODE=auto`

实际执行路径：

- 专用任务：`knowledge_import`、`embedding_refresh`、`report_generate`
- 通用命令任务：`today_analysis`、`refresh_data`、`fast_forecast`、`report_only`、`health_check`、`retrain_model`、`model_auto_optimize`
- 数据同步专用任务：`sync_core_data`

Celery worker 当前监听默认队列，尚未明确任务类型到 queue 的分层。

## 7. 当前任务日志写入逻辑

- `save_task_record` 会同时 upsert `task_runs` 与 `task_logs`。
- `run_command_task` 写文件日志，然后把末尾文本写入 `task_logs.log_text`。
- `_run_python_task` 把结构化结果序列化后写入 `task_logs.log_text`。
- `task_manager` 仍保留 legacy fallback 写入路径。

问题：

- `task_logs` 不是事件流模型，缺少多条步骤日志。
- 无分页。
- 无 level/step。
- 失败任务难以稳定取“最后一条 error 日志”。

## 8. 当前前端任务中心展示逻辑

相关文件：

- `frontend/src/pages/task/TaskCenterPage.tsx`
- `frontend/src/services/taskApi.ts`
- `frontend/src/api.ts`

现状：

- 展示任务列表、调度任务、失败重试、告警。
- 支持触发 Knowledge/Embedding/Report 任务。
- 支持取消、重试、查看日志。

问题：

- 页面存在历史编码乱码，字段语义不够可解释。
- 缺少 queue、timeout、retry lineage、worker、celery task 等生产字段展示。
- 日志查看不支持分页和结构化步骤。
- 任务健康只在后端简单返回 execution_mode/celery_available。

## 9. 当前缺失的生产化能力

1. 统一任务生命周期枚举与兼容映射。
2. 幂等 key 与 payload hash。
3. 去重窗口。
4. 默认 timeout_seconds 与 max_retries。
5. 超时状态和 timeout_at。
6. retry lineage。
7. 取消原因和 cancelled_at。
8. worker 侧取消/超时检查。
9. 结构化日志分页。
10. 队列分层和健康统计。
11. 前端任务详情可解释。

## 10. P4 改造计划

1. 新增 `backend/app/services/task_runtime.py`，集中管理状态、队列、超时、重试、幂等 key 和 payload hash。
2. 新增 Alembic migration `0007_task_runtime_productionization.py`，只扩列和加索引，不删除旧字段。
3. 增强 `task_repository.py`：
   - 保存新增字段；
   - 查询任务详情带新增字段；
   - 支持幂等查询；
   - 支持日志分页；
   - 支持 queue/status summary。
4. 增强 `dispatcher.py`：
   - 创建任务时写入 queue、timeout、max_retries、idempotency；
   - active 重复任务返回已有 task_id；
   - Celery 使用 queue_name 投递。
5. 增强 `tasks.py`：
   - 命令任务用轮询替代阻塞 `subprocess.run`，支持取消和超时；
   - Python 任务执行前后检查取消和超时；
   - 写入结构化步骤日志。
6. 增强 `task.py` API：
   - 日志分页；
   - 取消原因；
   - retry max_retries 校验；
   - health 返回 redis/celery/worker/queue/status summary。
7. 轻量重写前端任务中心页面与 task service，恢复中文可读性并展示新增字段。
8. 新增 P4 单测并执行 P1/P3 回归。
