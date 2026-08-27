# 执行计划

1. 读取最新主项目基线、RAG 恢复任务与工程规则。
2. 建立 Git、配置、数据库、Qdrant 与发布状态检查点。
3. 将发布数据库连接安全写入 Git 外配置并做脱敏校验。
4. 启动独立发布 Worker，执行 `validate` 与 `publish`。
5. 验收 PostgreSQL current、Qdrant Alias、Search、QA 和批量查询。
6. 修复实测发现的 BM25 运行资产缺失，重启后端加载 Worker 客户端配置。
7. 运行定向回归、秘密扫描，记录回滚路径并提交证据。
