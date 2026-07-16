# 数据库迁移说明

本目录用于阶段二后的数据库结构治理。迁移脚本必须保持幂等，重复执行不能破坏已有表。

当前迁移：

- `001_create_model_registry.sql`：模型版本注册表、迁移日志表、最新 active 模型视图。
- `002_create_prediction_tracking.sql`：逐小时预测追踪表、近期模型误差视图。
- `003_create_model_evaluation_runs.sql`：候选模型评估与对比记录。
- `004_create_monitoring_metrics.sql`：数据、模型、LLM 和流水线监控指标。
- `005_create_model_ops_tables.sql`：模型日级表现、重训任务、候选模型对比和审计日志。
- `006_create_report_approval.sql`：报告审批状态记录，为企业级落地预留。
- `007_create_ai_report_review_runs.sql`：AI 报告审批流正式表，记录待审核、已通过、已驳回、已派发和派发许可。
- `008_create_predictions_normalized.sql`：标准化预测结果与发布记录。
- `009_create_web_platform_tables.sql`：Web 平台策略建议、异常解释、报告审核、任务日志等表。
- `010_create_ai_assistant_tables.sql`：AI 问答会话、消息、工具调用日志和 Prompt 模板表。
- `011_create_ai_chat_feedback.sql`：AI 问答反馈表，记录点赞、点踩和 trace_id，支撑第一阶段助手验收闭环。
- `versions/0013_t001_model_fact_source.py`：为 `model_registry` 增加 domain/target、artifact、schema 与生命周期字段，并建立同一 domain+target 唯一 Active 的部分唯一索引；downgrade 仅移除新索引，不删除历史字段或数据。

执行方式：

```powershell
python -c "from automation_common import load_config; from database_utils import apply_database_migrations; apply_database_migrations(load_config(), log=print)"
```

说明：真实数据库连接仍通过 `.env` / 环境变量提供，不在 SQL 或配置文件中保存密码。

迁移只能由显式部署/运维流程执行；任何 GET、列表、详情、Active 查询和预测读取入口不得自动调用迁移。
