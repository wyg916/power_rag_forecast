# 功能保持清单

- 路由与三个策略子页键保持不变：`strategy-high`、`strategy-storage`、`strategy-review`。
- 总览保留区域、刷新、导出策略、策略配置、日视图/列视图和五张 KPI。
- 储能保留区域、执行对象、刷新、导出策略、设备切换、反馈详情和七列表格。
- 人工复核保留区域/风险/状态/搜索/清除筛选、刷新、导出、禁用批量动作、八列表格、分页、查看与复核入口。
- 权限过滤、人工复核状态、不可变审核历史、详情数据和按钮 handler 未改变。
- 全局 AI 入口与 Drawer 会话逻辑未改变。
- 页面业务数据仍来自 PostgreSQL → Backend Repository/Service → API → 前端状态链路；未增加前端硬编码或成功态 fallback。
