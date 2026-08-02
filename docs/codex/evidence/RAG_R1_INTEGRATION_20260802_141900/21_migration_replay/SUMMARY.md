# RAG-R1 PostgreSQL 隔离迁移回放

- 结果：`PASS`。
- 目标门禁：仅 `postgres@localhost:5432/postgres`。
- 隔离对象：`beta10d_rag_r1_20260802_071138_17420` 及其绑定受限角色。
- 回放：`upgrade head` → `downgrade 0017_day6_operational` → `upgrade head`，三个命令返回码均为 0。
- 第一次 head 结构 SHA-256：`da429eb82a09c94a9cd8ab6b8e0dc463ac38e6772e132f1346684ec7704830b0`。
- 第二次 head 结构 SHA-256：`da429eb82a09c94a9cd8ab6b8e0dc463ac38e6772e132f1346684ec7704830b0`。
- public 前后 revision：`0017_day6_operational`。
- public 前后结构 SHA-256：`99e6c492722ad47985a6b3452233ce286b25c4c98636f143546c3d59bb5d4bd2`。
- public 写入：0；正式 migration：未执行。
- 清理：临时 Schema 已删除，临时角色已删除，残留 0。
- 机器可读证据：`migration_replay.json`。

## 回滚

本包没有修改 public 数据库。代码回滚使用 `git revert <本包提交>`；隔离演练对象已经按精确名称清理，无需数据库恢复。
