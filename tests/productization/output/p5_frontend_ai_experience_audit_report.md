# P5-0 前端体验现状审计报告

生成时间：2026-06-19（Asia/Shanghai）

## Git 信息

- 当前分支：`p5-frontend-ai-experience`
- P5 基线：`5b597b7 docs: add P4 branch and smoke closure report`
- 工作区：P5 审计开始前干净。
- 本报告仅审计和规划，不做 P5 之外功能开发。

## 1. 首页现状

- 当前首页文件：`frontend/src/pages/dashboard/DashboardPage.tsx`
- 数据聚合：`frontend/src/services/dashboardApi.ts`
- 当前首页展示：预测核心指标、风险预警、24 小时价格趋势、储能建议、最新报告、任务日志、快捷入口。
- 已有 loading/empty/error：通过 `DataStateBanner`、`MetricGrid` 和 `SectionCard` 局部支持。
- 缺口：
  - 首页更像业务演示页，不是运营状态驾驶舱。
  - 未直观看到 P1 数据新鲜度、P3 RAG health、P4 task health、DB/Celery/Redis 状态。
  - 告警摘要没有统一聚合数据过期、任务失败、RAG fallback、预测落后和回测风险。

## 2. 数据中心现状

- 当前页面：`frontend/src/pages/data/DataCenterPage.tsx`
- 聚合服务：`frontend/src/services/dataApi.ts`
- 已接入 P1：
  - `GET /api/data/catalog`
  - `GET /api/data/fields`
  - `GET /api/data/freshness`
  - `POST /api/data/sql/query`
- 当前展示：数据接入流程、质量概览、数据目录、只读 SQL、数据新鲜度、PostgreSQL 表浏览、导入导出记录。
- 缺口：
  - 核心表卡片缺少“是否为空 / 是否支撑预测 / freshness 中文解释”的业务化表达。
  - 字段详情目前主要在抽屉中以文本展示，可读性不足。
  - SQL 入口已有只读查询能力，但默认 limit、敏感表拦截提示和失败原因需要更显眼。
  - 预测支撑提示尚未聚合为一组清晰判断。

## 3. 预测中心现状

- 当前页面：`frontend/src/pages/forecast/ForecastCenterPage.tsx`
- 聚合服务：`frontend/src/services/forecastApi.ts`
- 当前展示：最新预测曲线、预测明细、峰谷分析、策略洞察、导出 CSV。
- P2 输出存在：
  - `output/p2/metrics.json`
  - `output/p2/backtest_report.md`
  - `output/p2/feature_schema.json`
  - `output/p2/leakage_check_report.md`
  - `output/p2/leakage_check_result.json`
- 缺口：
  - 前端无法直接读取 P2 文件。
  - 后端 `backend/app/api/v1/endpoints/model.py` 目前只有 active/metrics/errors/retrain-suggestion，缺少 P2 backtest/schema/leakage 只读接口。
  - 预测中心未展示 baseline 对比、schema gate、leakage gate、peak/spike/extreme_weather 指标。

## 4. AI 助手现状

- 当前页面：`frontend/src/pages/assistant/AssistantPage.tsx`
- 当前能力：
  - 普通用户默认只显示 chat/FAQ。
  - admin/developer 可开启开发者模式，显示 tools/trace/RAG 细节。
  - 使用 `answer_style`、`model_provider`、`debug` 调用现有 AI API。
- 已有安全分层：
  - `developerMode && canUseDeveloperMode` 才显示 trace/tools/evidence debug。
- 缺口：
  - 普通模式回答仍以原始文本为主，数据来源表、字段、时间范围、记录数、查询摘要、查不到原因没有结构化卡片。
  - RAG evidence 在普通模式中不够折叠和业务化。
  - 失败回答缺少“失败原因 / 可检查项 / 下一步建议”固定区块。

## 5. 任务中心现状

- 当前页面：`frontend/src/pages/task/TaskCenterPage.tsx`
- 当前能力：
  - 已展示 P4 生命周期字段：status、progress、queue_name、execution_mode、retry_count、created_at、started_at、finished_at、timeout_seconds、worker_id、celery_task_id。
  - 已支持取消、重试、查看分页日志、运行健康、队列概览。
- 缺口：
  - 详情抽屉缺少状态时间线、最后一条 error log、retry lineage 的业务化展示。
  - 取消/重试按钮还没有按状态禁用。
  - failed/timeout/cancelled 视觉提示已有颜色，但处理建议可进一步强化。

## 6. 知识库页面现状

- 当前页面：`frontend/src/pages/knowledge/KnowledgeBasePage.tsx`
- 当前能力：
  - 已展示 P3 RAG health。
  - 展示 embedding provider、embedding dim、chunk count、embedded count、model path exists/readable、fallback reason。
  - 支持知识检索 smoke。
- 缺口：
  - 可以被首页和设置页复用为系统状态摘要。

## 7. 系统设置/状态页现状

- 当前页面：`frontend/src/pages/settings/SettingsPage.tsx`
- 聚合服务：`frontend/src/services/settingsApi.ts`
- 当前接口：
  - `GET /api/settings/config`
  - `GET /api/settings/health`
  - `GET /api/security/me`
  - `GET /api/security/permissions`
- 当前展示：用户管理、权限矩阵、参数配置、接口配置、基础健康信息。
- 缺口：
  - 未聚合展示 RAG / LLM / Redis / Celery / DB / Alembic 运行态。
  - LLM provider 和 API key 安全提示不够清晰。
  - 当前用户、角色、权限摘要可以更直接。

## 8. Loading / Empty / Error 状态

- 已有公共组件：`DataStateBanner`、`EmptyState`、`SectionCard` loading。
- 大多数页面有 loading 和 error banner。
- 缺口：
  - 结构化卡片级 empty/error 不均匀。
  - 任务日志为空时已有兜底文本；预测 P2 摘要缺失时还需兜底。
  - AI 失败回答需要固定结构。

## 9. 已可复用接口与需新增接口

已可复用：

- 数据中心：`/api/data/catalog`、`/api/data/fields`、`/api/data/freshness`、`/api/data/sql/query`
- 任务中心：`/api/tasks`、`/api/tasks/health`、`/api/tasks/{task_id}`、`/api/tasks/{task_id}/logs`
- 知识库/RAG：`/api/knowledge/health`
- 系统：`/api/health`、`/api/db/health`、`/api/settings/health`、`/api/ai/local-model/status`
- 权限：`/api/security/me`、`/api/security/permissions`

需新增只读接口：

- `GET /api/models/backtest/summary`：读取 `output/p2/metrics.json` 和 `backtest_report.md`，返回 baseline/backtest 摘要。
- `GET /api/models/feature-schema`：读取 `output/p2/feature_schema.json`，返回 schema 字段数量、target、segment columns 和字段样例。
- `GET /api/models/leakage-check`：读取 `output/p2/leakage_check_result.json` 和 `leakage_check_report.md`，返回 leakage gate 摘要。

这些接口只读本地 P2 输出文件，不开放写操作，不改变预测模型逻辑。

## 10. P5 改造计划

1. 新增只读 model summary 接口，服务预测中心读取 P2 backtest/schema/leakage。
2. 首页改造为运营驾驶舱，聚合数据新鲜度、任务 health、RAG health、系统 health、预测和回测风险。
3. 数据中心增强核心表状态卡、字段详情可读性、只读 SQL 风险提示和预测支撑提示。
4. 预测中心新增 P2 工程化摘要：baseline、场景指标、schema gate、leakage gate、模型建议。
5. AI 助手普通模式新增业务化回答结构卡，debug 信息继续仅 admin/developer 可见。
6. 任务中心增强状态时间线、错误日志摘要、按钮状态和 retry lineage。
7. 设置页新增系统状态概览，展示 Auth/DB/Task/RAG/LLM，隐藏真实 API key。
