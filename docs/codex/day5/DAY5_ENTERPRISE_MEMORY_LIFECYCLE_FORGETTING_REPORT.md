# Day5 Enterprise Memory Lifecycle / Forgetting V1 闭环报告

## 1. 结论

`DAY5 / ENTERPRISE-MEMORY-LIFECYCLE-FORGETTING-V1 = PASS（本地开发/预发布等效）`。

本阶段从 Day4 PASS 提交 `1c274ffe0798911cf9026d5c0ba3c70301da9a72` 单线开发，补齐确定性 TTL/Decay、Cold/Archive、Legal Hold、软删除、异步物理删除、失败重试、删除证明和后台 Worker。未进入 Day6，未执行生产发布或生产切流。

## 2. 基线、分支与检查点

- 唯一 parent SHA：`1c274ffe0798911cf9026d5c0ba3c70301da9a72`
- 分支：`codex/day5-enterprise-memory-lifecycle-v1`
- 独立 worktree：`E:\智能运营分析项目\.codex_tmp\worktrees\day5_enterprise_memory_lifecycle`
- PRE migration head：`0020_enterprise_memory_core_v1`
- PRE DB fingerprint：80 tables / 8 views / 47 sequences / 37 routines
- PRE 检查点：`backups/phase3/20260810_152633275_DAY5_ENTERPRISE_MEMORY_LIFECYCLE_PRE`
- 证据目录：`docs/codex/evidence/DAY5_ENTERPRISE_MEMORY_LIFECYCLE_20260810_152633`

Ancestry 审计确认 Day3B `6e3f7e85459a0cd47c2fedcb6d7a212d0e5f8158` 是 Day4 的直接祖先，二者之间只有 Day4 闭环提交，无 merge、cherry-pick 或未审计分叉。包含用户未提交 UI 内容的主工作树全程未修改。

## 3. 数据库与生命周期模型

- 新增唯一 Alembic head `0021_memory_lifecycle_v1`，直接继承 `0020_enterprise_memory_core_v1`。
- `ai_memory_records` 新增 `last_used_at`、`usage_count`、`soft_deleted_at`、`delete_requested_at`；状态增加 `delete_pending`。
- 新增 `ai_memory_legal_holds`、`ai_memory_deletion_jobs`、`ai_memory_deletion_proofs` 三张表。
- Outbox 增加 `dead_letter`；删除任务支持 pending/running/partial/completed/failed/blocked。
- `ai_memory_purge` 为受控 `SECURITY DEFINER` 函数：运行身份没有内容表直接 `DELETE` 权限；函数只接受处于 processing 的匹配删除事件，并在事务内清理 Record、Version、Relation 与过期 Outbox。
- Usage、Admission、State Transition 保留无内容审计；删除证明只保留内容哈希、版本集合哈希、作用域、删除结果和时间，不保留明文内容。

隔离 schema 完成 `0020 → 0021 → 0020 → 0021`；公共库最终重放相同往返成功。最终公共指纹为 83 tables / 8 views / 47 sequences / 38 routines，十张 Memory/Lifecycle 表均为 0 行。

## 4. 业务行为与安全边界

- TTL 状态与有效分数完全由显式输入、当前时间、importance、confidence、last-used、usage-count、memory type 和状态确定。
- active 可降为 cold；到期 active/cold 首轮归档，后续生命周期轮次请求删除。
- archived 默认不参与召回；治理场景可显式 `include_archived`。
- 用户只能删除自己的同 tenant/workspace/agent 记忆；管理员跨用户操作仍必须同 tenant/workspace/agent，跨租户 fail-closed。
- Legal Hold 仅授权管理员可设置/释放；删除请求前或请求后的 Legal Hold 均阻断物理删除，释放后可幂等恢复同一任务。
- 删除请求先软删除并退出召回，再由 Outbox Worker 执行；故障注入后为 partial/failed，可重试，达到阈值进入 dead-letter。
- 重复删除返回同一删除任务和 proof，不制造重复副作用。
- 当前 V1 没有独立 Memory 向量索引、搜索副本或 Memory cache，因此证明明确记录 `not_applicable_current_v1`，不伪造传播能力。

## 5. 运行时与启动幂等

新增独立 Day5 Memory Outbox Worker，并接入 `run_project.bat` 的 start/status 健康门禁。Worker 使用既有最小权限运行身份，通过表/函数契约判断 0021 就绪，不扩大权限读取 `alembic_version`；重复启动复用健康进程，陈旧进程仅按精确 PID 终止后重建，另提供显式 stop 命令用于回滚和 RC worktree 切换。

Docker Desktop、PostgreSQL、Redis、Celery、Qdrant、Backend、Frontend 在 PRECHECK 及最终 SHA 启动验收中均通过；最终 SHA 上 `run_project.bat` 连续运行两次，第二次复用健康服务并验证幂等。

## 6. 验证结果

- Alembic：唯一 head `0021_memory_lifecycle_v1`。
- 最终隔离联合矩阵：45 passed / 0 failed / 0 errors；临时 schema、运行角色、owner role 残留均为 0。
- Day5 static + launcher：8 passed / 2 isolated-only skipped。
- Day3B RAG smoke：28 passed。
- Frontend：TypeScript/Vite production build PASS，3,675 modules。
- 公共库只读审计：Migration 之外 Seed=0、业务同步=0、模型激活=0、RAG Alias 写入=0；Active model 和四张事实表水位与 PRE 一致；RAG-R1 保持 rolled_back/current=null。
- Qdrant 健康门禁：只读 health，write_operations=0、persistent_candidate_mutations=0、alias targets=[]。
- 全仓诊断：916 passed / 34 skipped / 46 failed / 32 errors。与 Day4 的 914 passed / 32 skipped / 46 failed / 32 errors 相比，非通过项规模未增加；失败/错误均属于历史隔离运行器、缺失模型/测试资产、旧 migration-head 断言或既有外部依赖，未据此宣称全仓全绿。
- `git diff --check`、Python compile、tracked manifest 增量核对和最终 Git clean 均通过。

## 7. 回滚

1. 停止 Day5 Worker：`python scripts/day5_memory_worker_runtime.py ... stop`。
2. 在已核验的本地 PostgreSQL 上执行 `alembic downgrade 0020_enterprise_memory_core_v1`；隔离与公共库均已验证此路径。
3. 对 Day5 提交执行普通 `git revert <day5_sha>`；不得修改或清理 UI 主工作树。

当前十张 Memory/Lifecycle 表均为空，因此回滚不涉及业务内容恢复。若未来表内已有数据，必须先导出受控备份并处理 Legal Hold/删除证明保留策略，不能直接 downgrade。

## 8. 剩余边界

- 本 PASS 是本地开发/预发布等效结论，不等于生产人工签署、生产切流或生产数据保留策略批准。
- 完整 Procedural Memory、Skill Evolution/Canary、跨系统 Memory 向量索引传播和 ChatBI 不在 Day5。
- Day5 PASS 后只允许执行 RC-CONVERGENCE CHECKPOINT；更新后的 RC 统一门禁通过前不得进入 Day6。
