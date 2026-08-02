# Runtime RT4B embedding profile 准入接收证据

- 来源提交：`e0a437de0d53635ce46c9cd68e70810f021cbea4`。
- 接收 3 个文件、`+86/-8`；仅修改 release profile 准入、对应测试和 RT4B 原证据。
- provider、model、approved version、dimension=1024、model SHA-256 与 sparse profile 必须逐项一致。
- `pytest tests/test_rag_enterprise_release_service.py -q`：`19 passed in 0.74s`。
- `git diff --cached --check`：PASS；敏感扫描在提交前执行。
- 当前只验证 profile 契约，未加载 BGE 权重；PostgreSQL/Qdrant/网络写入 0。
- 回滚：普通 `git revert <RT4B-integration-commit>`；无外部状态需要恢复。
