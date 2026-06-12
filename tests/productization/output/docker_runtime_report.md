# Docker Compose ???????

- ?????2026-06-09 12:07:01
- ????`pass`
- Compose config???
- ??????????

## ????

```text
NAME                               IMAGE                            COMMAND                  SERVICE         CREATED        STATUS                   PORTS
power-trading-ai-backend-1         power-trading-ai-backend         "/app/docker/backend…"   backend         11 hours ago   Up 8 minutes (healthy)   0.0.0.0:8000->8000/tcp
power-trading-ai-celery_worker-1   power-trading-ai-celery_worker   "/app/docker/backend…"   celery_worker   11 hours ago   Up 8 minutes             8000/tcp
power-trading-ai-frontend-1        power-trading-ai-frontend        "docker-entrypoint.s…"   frontend        11 hours ago   Up 8 minutes (healthy)   0.0.0.0:8080->80/tcp
power-trading-ai-postgres-1        postgres:16-alpine               "docker-entrypoint.s…"   postgres        13 hours ago   Up 8 minutes (healthy)   0.0.0.0:5433->5432/tcp
power-trading-ai-redis-1           redis:7-alpine                   "docker-entrypoint.s…"   redis           13 hours ago   Up 8 minutes (healthy)   0.0.0.0:6380->6379/tcp
```

## ????

| ??? | ?? | ?? |
|---|---|---|
| backend_health | ?? | `{"ok": true, "platform": "售电交易 AI 辅助决策平台", "version": "v2.11.2"}` |
| db_health | ?? | `{"ok": true, "active": "postgresql", "message": "PostgreSQL 主库连接正常。"}` |
| tasks_health | ?? | `{"ok": true, "execution_mode": "celery", "celery_available": true, "message": "ok"}` |
| frontend_health | ?? | `ok
` |
| frontend_proxy_tasks_health | ?? | `{"ok": true, "execution_mode": "celery", "celery_available": true, "message": "ok"}` |
| frontend_root | ?? | `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <title>售电交易 AI 辅助决策平台</title>
    <script type="module" crossorigin src="/assets/index-BE11Bxwh.js"></script>
    <link rel="modulepreload" crossorigin href="/assets/vendor-antd-D3RKmqKf.js">
    <link rel="stylesheet" crossorigin href="/assets/index-FsapERbo.css">
  </head>
  <b` |
| tasks_list | ?? | `{"tasks": [{"task_id": "runtime_cancel_running_3557137b84", "run_id": "20260609_120658", "kind": "runtime_check", "status": "cancel_requested", "started_at": "2026-06-09 12:06:58", "ended_at": null, "finished_at": null, "duration_seconds": null, "error_message": "", "progress": 10.0, "message": "can` |
| knowledge_stats | ?? | `{"available": true, "documents": 33, "chunks": 36}` |
| reports_latest | ?? | `{"report_id": "latest", "run_id": "latest", "available": true, "report_path": "/app/自动化输出/current/电价智能分析综合报告.docx", "generated_at": "2026-06-09 00:46:34.556156", "fallback_used": false, "summary": {}, "source": "/app/自动化输出/current"}` |

## PostgreSQL ? Alembic

- PostgreSQL runtime?`pass`
- Alembic version?`0005_task_runtime_observability`

| ?/?? | ?? |
|---|---|
| task_runs | ? |
| task_logs | ? |
| audit_logs | ? |
| ai_traces | ? |
| kb_documents | ? |
| kb_chunks | ? |
| raw_market | ? |
| raw_weather | ? |
| raw_load | ? |
| raw_renewable | ? |
| feature_importance | ? |
| task_runs.execution_mode | ? |
| task_runs.cancel_requested | ? |
| task_runs.worker_id | ? |
| task_runs.celery_task_id | ? |

## Redis / Celery / ????

- Redis?`pass`?redis ping ok
- Celery?`pass`?worker_count=1
- ????????`pass`

## ???????

| ?? | ?? | ???? | ?? |
|---|---|---|---|
| ????? | success | celery | kb_documents/kb_chunks |
| Embedding ?? | success | celery | kb_chunks.embedding_json |
| ???? | success | celery | /app/自动化输出/logs/celery_task_report_only_20260609_004434.log |

## ????

| ??? | ?? |
|---|---|
| root_ok | ?? |
| api_proxy_ok | ?? |
| tasks_api_ok | ?? |
| knowledge_api_ok | ?? |
| reports_api_ok | ?? |

## BGE / Embedding ??

- ?? embedding refresh provider?`local_hash`?model?`local-hash-bge-small-zh-v1.5-compatible`?
- ?? Compose smoke test ?????? local/hash embedding ????? BGE ??????????? BGE ?????
- ?????? BGE ?????? .env.docker ?? `RAG_EMBEDDING_PROVIDER=sentence_transformers` ???? `RAG_EMBEDDING_MODEL_PATH`????????????

## ????

- AUTH_REQUIRED was set to 0 only in generated .env.docker for this runtime smoke test because formal JWT/login is a later item.
- Celery worker starts successfully but imports are relatively heavy; health checks should allow enough startup time.
- BGE model directory is not mounted in this smoke deployment, so embedding refresh uses configured fallback rather than real BGE.
- Celery worker currently runs as root inside python:3.11-slim image; production should add a non-root user.

## ????????

| Pattern | Count |
|---|---:|
| api_key_prefix | 0 |
| deepseek_api_key_assignment | 0 |
| openai_api_key_assignment | 0 |
| authorization_bearer | 0 |
| database_url_assignment | 0 |
| postgres_url_with_password | 0 |
| postgres_password_assignment | 0 |
