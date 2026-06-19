# P5 前端体验与 AI 输出优化报告

生成时间：2026-06-19（Asia/Shanghai）

## 1. Git 信息

- 当前分支：`p5-frontend-ai-experience`
- P5 起点：`5b597b7 docs: add P4 branch and smoke closure report`
- P5 commit：待提交。本报告随 `feat: improve frontend dashboard and AI answer experience` 一起提交，准确 hash 以提交后 `git rev-parse HEAD` 为准。
- 是否触碰 main：否。
- 是否强推 main：否。
- 是否提交真实密钥：否。

## 2. 改造摘要

- 新增 P2 只读模型摘要 API：
  - `GET /api/models/backtest/summary`
  - `GET /api/models/feature-schema`
  - `GET /api/models/leakage-check`
  - 同时保留 `/api/model/...` 兼容别名。
- 首页改造为运营驾驶舱：
  - 聚合数据新鲜度、DB health、任务中心 health、RAG/BGE health、P2 backtest baseline。
  - 展示统一运营关注项，提示数据过期、任务失败/超时、RAG fallback、P2 gate 风险。
- 数据中心增强：
  - 核心预测表 `raw_market`、`raw_load`、`raw_weather`、`forecast_results`、`raw_renewable` 展示可用/空表/缺失和时间范围。
  - 只读 SQL 区域明确白名单、敏感表、写操作、多语句、危险函数和最大返回行数限制。
  - 查询异常在页面内固定展示。
- 预测中心增强：
  - 新增“模型评估”页签。
  - 展示 baseline、整体指标、高峰指标、尖峰指标、极端天气指标、feature schema gate、leakage gate、baseline 对比。
- AI 助手增强：
  - 普通模式展示表名、字段、时间范围、记录数、查询摘要、查不到或拒绝原因。
  - Trace、工具调用、RAG 分数等 debug 内容仍仅在 admin/developer 模式展示。
- 任务中心增强：
  - 按状态禁用取消/重试按钮。
  - 任务详情展示生命周期时间线、最后错误摘要和 retry lineage。
- 设置页增强：
  - 新增“系统状态”页签，聚合认证、DB、任务运行态、RAG/BGE、LLM、settings health。
  - 前端展示配置做二次脱敏，不展示真实 API key、token、secret 或 password。

## 3. 后端只读接口

- 文件：`backend/app/api/v1/endpoints/model.py`
- 读取文件：
  - `output/p2/metrics.json`
  - `output/p2/backtest_report.md`
  - `output/p2/feature_schema.json`
  - `output/p2/leakage_check_result.json`
  - `output/p2/leakage_check_report.md`
- 接口只读 P2 输出文件，不触发训练、预测、写库或模型切换。
- 权限：沿用 `model:read`。

## 4. 安全与约束确认

- 未修改 P1 SQL 安全策略。
- 未开放写 SQL。
- 未修改预测模型算法、训练逻辑或预测输出逻辑。
- 未回退 P2 feature schema、leakage check、backtest 机制。
- 未回退 P3 RAG health / Docker BGE 挂载检查。
- 未回退 P4 task lifecycle / idempotency / retry / cancel / logs / health。
- 未删除 Docker volume、数据库 volume 或模型权重。

## 5. 测试结果

- `python -m py_compile backend/app/api/v1/endpoints/model.py`：通过。
- `python -m pytest tests/test_p5_model_readonly_api.py -q --durations=20`：4 passed。
- `cd frontend && npm run build`：通过。
- P1 回归：`python -m pytest tests/test_data_trust_service.py tests/test_ai_database_table_freshness.py -q --durations=20`：11 passed。
- P3 回归：`python -m pytest tests/test_p3_rag_docker_consistency.py -q --durations=20`：4 passed。
- P4 回归：`python -m pytest tests/test_p4_task_lifecycle.py tests/test_p4_task_idempotency.py tests/test_p4_task_retry_cancel_timeout.py tests/test_p4_task_logs.py tests/test_p4_task_health.py -q --durations=20`：13 passed。

## 6. 前端构建结果

- 构建命令：`npm run build`
- 结果：通过。
- 说明：本轮涉及前端体验改造，已执行生产构建。

## 7. Docker Smoke

- 本轮 P5 未执行新的 Docker smoke。
- 原因：P5 改造集中在前端展示、只读 model summary API 和页面聚合逻辑；已通过后端编译、接口测试、P1/P3/P4 回归和前端生产构建验证。
- 建议：进入 P6 前如需线上态复核，可复用 P4 Compose 环境再执行一次轻量 `/api/health`、`/api/tasks/health`、`/api/knowledge/health`、P2 model summary API 和前端页面访问 smoke。

## 8. 已知问题

- P5 未新增 Playwright 浏览器截图验收；当前以前端生产构建和后端回归测试为准。
- P2 摘要接口依赖 `output/p2` 文件存在；文件缺失时接口会返回 `available=false`，页面以 warning/empty 状态展示。
- 首页和设置页聚合多个运行态接口，单个接口异常不会阻塞页面，但会在 `DataStateBanner.partialErrors` 中提示。

## 9. 是否建议进入 P6

本地 P5 验收已通过。若 P5 分支推送成功，可进入 P6；如果远程推送仍受网络阻塞，应先完成分支/tag 或 bundle 保护后再进入 P6。
