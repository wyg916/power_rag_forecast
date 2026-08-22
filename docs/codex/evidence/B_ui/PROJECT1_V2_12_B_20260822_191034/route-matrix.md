# B_UI 32 路由验收矩阵

以下 32 个业务路由在 1280x720、1366x768、1440x900、1920x1080 四档视口逐一检查，共 128 个路由-视口组合。

| 业务域 | 子路由 |
|---|---|
| 首页 | dashboard-overview |
| 数据中心 | data-overview、data-quality |
| 预测中心 | forecast-24h、forecast-history、forecast-model |
| 策略中心 | strategy-high、strategy-storage、strategy-review |
| AI 助手 | assistant-chat、assistant-tools、assistant-trace、assistant-faq |
| 报告中心 | report-daily、report-weekly、report-review、report-publish |
| 模型中心 | model-active、model-candidate、model-error、model-rollback |
| 知识库 | knowledge-policy、knowledge-index、knowledge-rag、knowledge-qa |
| 任务中心 | task-schedule、task-log、task-alert、task-retry |
| 系统设置 | settings-status、settings-user、settings-api |

每个组合检查：页面标题存在、唯一 Sticky Header、唯一全局 AI 悬浮按钮、文档无横向溢出、默认标题区副标题不可见、技术元数据块不可见、Raw 403 不可见、页面错误块不可见。最终结果：128/128 PASS。
