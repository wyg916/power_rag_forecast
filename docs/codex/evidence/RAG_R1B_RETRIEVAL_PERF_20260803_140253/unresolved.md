# 未解决项

1. Qdrant `127.0.0.1:6333` 不可达，无法用正式 Candidate 复现历史 P95 或执行优化后完整 50 题。
2. 历史 P95 6175.825ms 只有任务文档记录，仓库与运行资产没有对应原始 acceptance 报告，无法恢复历史阶段分布。
3. 现有 50 题文件标记 `human_verified=false`；即使运行环境恢复，也只能作为当前优化集，最终仍需人工确认后的正式黄金集复验。
4. 正式 reranker CPU 微基准优化后 warm P95 为 4158.143ms，仍高于 1500ms；完整链路目标尚未证明达成。
5. Recall、MRR、Citation、ACL 与 cold/warm cache hit/miss 四象限未完成 live 复验，当前不可交主控验收。
