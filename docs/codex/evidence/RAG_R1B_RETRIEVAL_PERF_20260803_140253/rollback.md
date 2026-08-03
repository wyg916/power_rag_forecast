# 回滚方案

- 起始分支：`beta10d/rag-r1b-retrieval-performance`
- 起始 HEAD：`ec78c569bd4036f23341e40b2d4d212a6f85177c`
- 起始工作树：干净。
- 本任务禁止数据库、迁移、配置、Compose、公共 API、release、alias 与 snapshot 变更，因此无需数据恢复。
- 本任务没有 PostgreSQL/Qdrant 写入；性能输出只位于本任务证据目录。
- 提交前可用本目录的基线哈希和 Git diff 精确核对；提交后由主控使用 `git revert <task_commit>` 回滚，禁止 reset。
