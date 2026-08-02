# 回滚

- 代码/测试修复提交：`3fcf2e436a1de614008f8d72da387bf5314413f7`；如需撤销，执行 `git revert 3fcf2e436a1de614008f8d72da387bf5314413f7`。
- 该提交包含 PostgreSQL 时间区间语法、无数据库错误优先级、外置电价资产根目录和测试隔离画像修复；回滚后旧兼容性失败会恢复。
- 数据库隔离 schema/role 已由运行器清理，无持久数据需要恢复；RAG-R1 Candidate、Qdrant、snapshot、alias 和 Published 状态未改变。
- 工作树 `frontend/node_modules` 是指向主项目同版本依赖的本地 junction，不属于 Git 提交；如需清理，应由用户在确认精确路径后移除该单一路径。
