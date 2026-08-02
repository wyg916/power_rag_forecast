# RAG-RT4 实施证据摘要

## 范围与检查点

- 分支：`codex/rag-enterprise-runtime`
- 基线：`e19be4c878fc3f00f564bce5f085827ba582578a`
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_182925_RAG_RT4_PRE`
- 本包仅新增 release/publish runtime 协议、fake 故障测试和本证据。

## 实施结果

- 注入式 `QdrantAdminControl`、`ReleaseFactStore`、`CacheInvalidator`，协议不暴露删除 Collection 能力。
- 实现 Candidate→Validated→Published→RolledBack，并对 validate/publish/rollback 提供幂等结果。
- 发布前强制完整门禁、ReleaseIdentity、Collection、tenant/published payload、Dense/Sparse profile 和 snapshot 校验。
- 发布清单独立保存 snapshot ID、alias before/after、前一 release，并明确 `snapshot_contains_alias=false`。
- 固定执行 alias compare-and-swap→PG current compare-and-swap→smoke→状态事实。
- PG current 失败立即回切 alias；切换后 smoke 失败同时恢复 alias 与 PG current。
- 补偿失败返回 `consistency_restored=false` 并保留 validated/published 记录及失败事实，禁止伪造成功。
- 成功发布后仅把旧 release 标记 superseded；成功回滚后标记新 release rolled_back，不删除新旧 Collection。
- 缓存协议只允许按 tenant/release ID 失效，不提供全局清空入口。
- 所有结果携带 elapsed_ms 与 5 分钟 RTO 是否达标。

## 测试

- 发布状态机与故障注入定向测试：`10 passed in 0.20s`。
- Release DTO、Schema 与运行时契约联合回归：`43 passed in 0.52s`。
- 覆盖 alias 失败、PG 失败、smoke 失败、补偿回切失败、显式 rollback 失败和 RTO 超时。
- 覆盖重复 validate/publish/rollback 无重复切换或写入。

## 外部影响与回滚

- 仅使用内存 fake；未连接 PostgreSQL、Qdrant、网络、缓存服务或真实模型。
- 未修改 Compose、配置、API、迁移、数据库、前端或正式 release。
- 未创建、切换、快照或删除任何真实 Collection。
- 提交后使用 `git revert <RAG-RT4-commit>` 回滚；本包没有外部数据状态需要恢复。
