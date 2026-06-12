from __future__ import annotations


TASK_MODE_DESCRIPTIONS = {
    "fast_forecast": "加载 Active 模型执行快速预测，不重新训练，并继续生成 AI 报告、落库和归档。",
    "refresh_fast_forecast": "先刷新数据，再加载 Active 模型快速预测，不重新训练。",
    "retrain_model": "完整重训模型，保存 candidate artifact，并继续生成报告和归档。",
    "model_auto_optimize": "回填真实值、更新误差记忆、执行退化判断，必要时触发候选模型重训与对比。",
    "refresh_data": "每天先更新数据，再执行预测、AI 报告、落库和归档。",
    "full": "跳过数据更新，直接执行预测、AI 报告、落库和归档。",
    "skip_prediction": "复用已有预测结果，仅生成 AI 报告、落库和归档。",
    "prediction_report_only": "运行预测和报告流程，不做数据刷新。",
    "model_ops_daily": "执行数据库闭环、真实值回填、误差监控和重训登记。",
    "health_check": "执行项目依赖、路径、数据库和关键文件健康检查。",
    "smoke_test": "执行轻量整体自检，用于快速确认环境未破坏。",
}
