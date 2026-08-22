# 未决项

- A 范围 P0 未决项：无。
- ChatBI Catalog 与 20 个 Golden 问题语义基础属于 C，本任务只记录依赖，不修改。
- 当前冻结输入是历史业务事实；不得标记为当前实时数据，策略发布门禁必须保持 fail-closed。
- 集成启动应为 Celery worker 使用唯一 nodename，并在接收首个预测请求前完成 queue health 预热。
