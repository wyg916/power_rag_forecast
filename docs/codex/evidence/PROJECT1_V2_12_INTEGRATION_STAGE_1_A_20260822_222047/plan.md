# Plan

1. 核验 Integration/Bootstrap 差异与 A 交付。
2. 创建外置可恢复检查点并以 `--no-ff` 合并 A。
3. 在 merge SHA 上执行 PostgreSQL/Celery/失败回滚/下游/重启读回门禁。
4. 写入报告与证据后停止；不合入 B/C。
