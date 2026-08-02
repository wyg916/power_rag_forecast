# RAG-R1 运行角色最小数据库权限闭环

- 状态：`PASS`。
- 固定目标：`localhost:5432/postgres`；管理身份仅用于 ACL 变更，应用身份为 `beta10d_forecast_login`，通过 `beta10d_forecast_runtime` 继承权限。
- 应用身份保持非超级用户、不可建库、不可建角色、不可复制、不可绕过 RLS、不可在 public Schema 创建对象。
- documents、versions、chunks、releases、release_items 保持仅 SELECT。
- 仅为 retrieval_runs、citations、rag_audit_events 新增 SELECT、INSERT；UPDATE、DELETE 均未授权，无序列权限需求。
- 运行登录身份没有直接表权限，所有本包权限均落在既有 NOLOGIN 组角色。
- 回滚探针在单一事务内 GRANT 后验证完整通过，再主动 ROLLBACK；恢复事实与前态逐字段一致，持久权限变化 0。
- 正式应用精确变化 6 个权限事实；第二次应用变化 0，幂等 PASS。
- 真实运行身份在同一事务内成功插入 retrieval run、citation、audit event 各 1 行并全部回滚；后续 UPDATE、DELETE、Release INSERT 均由 PostgreSQL 以 SQLSTATE `42501` 拒绝。
- 前后 Alembic 均为 `0018_rag_enterprise_r1`，public structure SHA 均为 `15d4fd97…e208be`，全部表内容指纹、RAG 行数完全一致；业务行持久写入 0。
- 定向单元测试 18 passed；py_compile、diff check PASS。

## 回滚

执行固定目标工具的 `--mode revoke`，仅撤销 `beta10d_forecast_runtime` 对三张追加表的 SELECT/INSERT；随后运行 `--mode verify`，预期只出现 6 个 `append_privilege_missing`，并用本目录 `pre_write` 快照复核业务表内容未变。代码使用 `git revert <commit>`。

Candidate 仍为 `candidate/is_current=false`；Qdrant alias/snapshot、Published/生产切换均未改变。
