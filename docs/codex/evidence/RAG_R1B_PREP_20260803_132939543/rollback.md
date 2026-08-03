# 回滚

- 主控合并：使用 `git revert -m 1 <merge_commit>`，禁止 reset。
- 任务边界文档：使用普通 `git revert` 回滚对应文档提交。
- 工作树：保留分支；如需移除，必须由主控先确认工作树干净，再逐个精确移除。
- PostgreSQL：不恢复已回显旧密码；新凭据故障时再次轮换为另一随机新密码。
- 本任务未修改 ACL、迁移、业务数据、Qdrant collection/alias/snapshot 或 release 状态。

