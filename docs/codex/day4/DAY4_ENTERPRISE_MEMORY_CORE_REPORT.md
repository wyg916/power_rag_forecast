# Day4 Enterprise Memory Core V1 闭环报告

## 1. 结论

Day4 在 Day2 的 `IdentityContext`、会话持久化、trace、tool log 与 conversation state 基础上，完成企业长期记忆核心 V1。实现范围严格止于 MemoryRecord、Version、Relation、Usage、Outbox、Admission、Semantic Memory、Episodic Memory、最小检索和 Context Budget；未进入 Day5，也未实现完整 TTL/Decay、物理删除传播、Legal Hold、完整 Procedural Memory 或 Skill Evolution。

## 2. 基线、检查点与证据

- 起始分支：`release/beta10d-agent-rc-20260807`
- 起始 SHA：`6e3f7e85459a0cd47c2fedcb6d7a212d0e5f8158`
- 执行分支：`codex/day4-enterprise-memory-core-v1`
- PRE 检查点：`backups/phase3/20260810_114349097_DAY4_ENTERPRISE_MEMORY_PRE`
- 证据目录：`docs/codex/evidence/DAY4_ENTERPRISE_MEMORY_20260810_115200`
- 数据库 schema-only 备份：PRE 检查点内 `database_schema_only.sql`，SHA-256 `96A92A8095D803A8E37C943D151FA035113CFEA0112FE1CE09B63DB75F441A5C`

检查点保存 Git 状态、diff、未跟踪清单、关键哈希、数据库影响与恢复说明。正式数据库迁移前，先在临时 schema/受限角色中完成 upgrade、downgrade、re-upgrade 和残留检查。

## 3. Migration、表与索引

- Migration：`0020_enterprise_memory_core_v1`
- Down revision：`0019_memory_identity_safety`
- 新增 7 张表：`ai_memory_records`、`ai_memory_versions`、`ai_memory_relations`、`ai_memory_usage`、`ai_memory_outbox`、`ai_memory_admissions`、`ai_memory_state_transitions`
- 物理索引 23 个：7 个主键索引、4 个唯一约束索引、12 个显式业务索引
- 关键索引覆盖：四维身份 scope、有效状态/类型/重要度/更新时间、内容哈希幂等、全文、来源、版本历史、关系 scope、usage trace、outbox dispatch、admission scope 与状态历史
- 运行身份对 7 表仅授予 `SELECT/INSERT/UPDATE`，`DELETE=false`

隔离迁移往返的第一次与第二次结构哈希一致；正式数据库已升级到 0020，升级后为 80 tables / 8 views / 47 sequences / 37 routines。

## 4. MemoryRecord 与状态机

MemoryRecord 统一复用 `tenant_id/workspace_id/user_id/agent_id/session_id/run_id`，支持 `semantic`、`episodic`，并为 `procedural` 预留候选状态。Semantic subject 明确区分 `user_fact/business_fact/system_fact`，Episodic 使用 `task_episode` 且强制绑定 session、run 与 occurred_at。

状态机支持 `draft/pending/active/cold/archived/deleted`。非法跳转 fail-closed；每次合法变化写入 `ai_memory_state_transitions`，Archive/Delete Request 同时写 Outbox，不执行物理删除。

## 5. Version、Relation、Usage 与 Outbox

- Version：更新时新增不可变版本，再切换 `current_version`；保留 `supersedes_version_id`、change reason、source、confidence 与 `created_by_run_id`。
- Relation：支持 `SUPPORTS/CONTRADICTS/SUPERSEDES/DERIVED_FROM/RELATED_TO`；关系两端均执行同一身份 scope 校验，冲突不删除旧事实。
- Usage：记录 memory/version、完整身份、session/run/trace、usage type、retrieved time 与 `used_in_answer`；与 assistant turn、trace 同一数据库事务提交。
- Outbox：支持 `MEMORY_CREATED/MEMORY_UPDATED/MEMORY_ARCHIVED/MEMORY_DELETE_REQUESTED`，以幂等键去重；数据库仍是事实源。本阶段未新增 Worker。

## 6. Admission

确定性 Admission 检查 Identity Scope、memory type、来源、confidence、importance、business value、重复、冲突、敏感/PII 与 TTL，结果为 `REJECT/SESSION_ONLY/LONG_TERM_CANDIDATE/LONG_TERM_ACCEPTED`。只有明确用户请求或已验证来源并满足阈值时才能直接接受；procedural 只能进入 Candidate。敏感内容只留下 hash 与拒绝审计，不进入可召回记录。

## 7. Semantic、Episodic、检索与 Context Budget

检索先用 materialized scoped CTE 限定 tenant/workspace/user/agent、状态、TTL 和 memory type，再执行 keyword/fulltext-compatible、recency、importance、confidence 融合排序，禁止全局召回后过滤。

Context Budget 分为 Current Session 600、Semantic 800、Episodic 500、RAG 1200、Tool Facts 1800 字符预算。优先级为当前业务事实 > Tool Verified Facts > RAG Authorized Evidence > Semantic > Episodic > 历史摘要；Memory 明确不得覆盖当前 RAG 权威事实。

现有 AI Assistant 已接入最小闭环：明确“请记住”写入；新会话可跨会话召回；召回使用写入 Usage；持久化或权限异常 fail-closed。前端未新增 Mock 或重构页面。

## 8. 验证结果

- 隔离 PostgreSQL：3 个纯单元测试 + 2 个隔离集成测试 PASS；覆盖 upgrade/downgrade/re-upgrade、Record、Version、Relation、Usage、Outbox、Admission、Semantic、Episodic、跨会话、跨用户、跨租户、冲突、事务、幂等、故障注入、状态机和 AI Assistant 端到端。
- Cross-user leakage：0；Cross-tenant leakage：0。
- Day2 Memory live regression：PASS；5 个越权操作均为 404，事务回滚残留 0。
- Day4 正式目标矩阵：60 passed / 2 isolated-only skipped / 0 failed / 0 errors。
- 全仓诊断矩阵：914 passed / 32 skipped / 46 failed / 32 errors；78 项均已分类，Day4 引入的迁移文件数量旧断言已修复。其余是未注入隔离数据库/模型资产/历史数据的环境门禁或历史迁移断言，不作为正式目标矩阵降级依据，详见证据 `27_full_regression_classification.md`。
- Frontend：TypeScript + Vite production build PASS，3,675 modules。
- Browser：登录标题、用户名、密码、登录按钮可见；1280px 横向溢出 0；console warning/error 0。
- RAG Day3 回归：Day3A/Day3B/Release Adapter 目标矩阵 PASS；正式集合、回滚态与发布边界保持不变。

## 9. 回滚

代码可回滚到起始 SHA 或从 PRE 检查点恢复逐文件原件。数据库执行 `alembic downgrade 0019_memory_identity_safety` 会按依赖逆序移除 7 张 Day4 表；如需恢复结构，可使用 PRE schema-only dump。Outbox 未配置外部 Worker，因此本阶段没有外部向量索引或删除传播需要补偿。

## 10. 剩余边界与风险

- 完整 TTL/Decay、物理删除传播、Legal Hold、完整 Procedural Memory、Skill Canary、ChatBI 与生产发布均留待后续阶段。
- 全仓全量 pytest 仍包含历史环境依赖债务；正式目标矩阵与隔离数据库矩阵已通过，但不能把全仓诊断结果描述为全绿。
- 当前仅完成本地开发/预发布等效验证，不代表生产切流或人工生产签署。
