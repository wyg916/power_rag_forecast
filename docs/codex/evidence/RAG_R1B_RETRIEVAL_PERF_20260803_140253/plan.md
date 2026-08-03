# RAG-R1B 检索性能任务执行记录

1. 已固定正式 Candidate、50 题现有评测集、BGE 1024 与正式 reranker；当前评测集 `human_verified=false`。
2. 已实现 auth/ACL、query embedding、sparse、dense、Qdrant、RRF、duplicate merge、parent expansion、reranker、Citation hash、PostgreSQL metadata、serialization、cache 的显式阶段字段；Candidate 路径不含真实 auth 和 PostgreSQL metadata，报告为未测而非伪计时。
3. 已在白名单内完成并行只读召回、模型/配置缓存、幂等预热、批处理保护、逐题端到端分段计时、live ACL 负向检索及强制优化前基线对照的 cold/warm cache 四象限工具。
4. 定向测试与幂等复跑通过；白名单、敏感信息和 diff 检查通过。
5. Qdrant `127.0.0.1:6333` 不可达，正式 50 题 baseline/after、质量门禁及四象限实测被阻塞，未标记 PASS。
6. 未执行 merge、cherry-pick、rebase、发布、snapshot、alias/release 切换或数据库写入。
