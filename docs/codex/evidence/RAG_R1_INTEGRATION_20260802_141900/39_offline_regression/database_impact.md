# 数据库影响

- 普通全仓回归运行于 `disabled-no-database` 模式，数据库依赖用例透明跳过。
- Day 3 隔离运行器创建一次性 schema/role，迁移至 `0018_rag_enterprise_r1` 后执行数据库证明；`public_match=true`，每次清理均为 `PASS`，残留 schema/role 均为空。
- 最终业务隔离回归仅改变一次性 schema 内的 `ai_traces`、`audit_logs`、`storage_devices`、`storage_soc_snapshots`、`strategy_execution_items` 和 `audit_logs_id_seq`，清理后不再存在。
- RAG-R1 保持 Candidate、`is_current=false`；未执行发布、准入写入、snapshot、alias 切换或生产切换。Qdrant Candidate 点数保持 8,339。
