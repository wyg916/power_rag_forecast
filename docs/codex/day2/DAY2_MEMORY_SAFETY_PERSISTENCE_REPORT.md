# Day2 记忆安全与持久化闭环报告

## 结论

**PASS（本地统一 RC / Day2 范围）**。

本次已完成 P0-MEMORY-SAFETY-AND-PERSISTENCE：身份上下文贯穿认证、API、服务、Repository、PostgreSQL 记忆与 Trace；跨用户、跨租户访问泄漏为 0；记忆写入具备事务、幂等、并发和失败回滚语义；正式持久化只使用 PostgreSQL；统一启动器已纳入 PostgreSQL、Redis、Qdrant、Backend、Celery 与 Frontend 的幂等闭环。

本结论不表示生产准入。RAG-R1 保持 `candidate / is_current=false`，未切换 alias，未激活模型，未执行生产发布。

## 实施结果

### 1. 权威身份上下文

- 新增 `IdentityContext`，统一携带 `tenant_id`、`workspace_id`、`user_id`、`role_ids`、`agent_id`、`session_id`、`run_id`。
- JWT 登录和后续请求均以数据库用户记录为权威身份来源；请求体中的 `tenant_id`、`user_id` 等覆盖字段由 Pydantic fail-closed 拒绝。
- 会话、消息、状态、工具调用、反馈和 Trace 的读写均按 `tenant_id + workspace_id + user_id + agent_id` 约束，并结合 `session_id/run_id` 追踪。
- 会话列表、分页、详情、标题修改、删除、反馈及 Trace 查询均进入同一身份边界；外部身份不可由前端声明。

### 2. PostgreSQL 唯一正式持久化

- 重写在线记忆路径，移除可达路径中的 JSON 成功态 fallback、在线自动迁移、异常吞噬和 MySQL `ON DUPLICATE KEY UPDATE`。
- PostgreSQL 写失败统一抛出持久化异常并由 API 返回 503；外部身份访问返回 404，避免资源存在性泄漏。
- 单轮问答将 Session、两条 Message、State、ToolCall 和 Trace 放入同一事务；任一环节失败时整轮回滚。
- 消息、工具调用、聊天反馈和回答反馈增加幂等键及唯一索引；并发重复请求最终只保留一组事实。

### 3. 迁移 0019

- 新增 `0019_memory_identity_safety`：补齐用户与 7 张 AI 记忆/Trace 表的身份列、幂等列、身份索引和受限运行角色所需 DELETE 权限。
- 历史无归属 Trace 标记为 `legacy_unowned`，不会被普通用户身份命中。
- 在隔离 schema/role 中完成 `upgrade head → downgrade 0018 → upgrade head`；两次 head 结构 SHA-256 完全一致。
- 隔离回放前后正式 `public` 结构 SHA-256 完全一致，隔离 schema/role 均已清理。
- 正式库当前 Alembic head 为 `0019_memory_identity_safety`。

### 4. 唯一 RC 一键启动

- `run_project.bat` 增加仅存于 E 盘忽略目录的稳定本地 JWT 签名密钥生成/复用逻辑，且不输出密钥。
- Qdrant 使用批准的 E 盘 runtime 配置，先执行资产与安全预检，再幂等 `docker compose up -d`，并对冷恢复增加有限重试。
- 启动闭环依次验证 PostgreSQL 身份与 Alembic、Redis、Qdrant TLS/ACL、Celery health task、Backend、Frontend 和综合健康状态。
- 新增 PATCH/DELETE 会话接口已登记权限矩阵，启动时权限覆盖检查保持 fail-closed。

## 验收结果

| 验收项 | 结果 | 核心证据 |
|---|---|---|
| 隔离迁移往返 | PASS | 0019→0018→0019；两次 head hash 一致；public hash 不变；隔离对象清零 |
| 并发与幂等 | PASS | 6 个并发重复写最终为 1 Session、2 Message、1 State、1 ToolCall、1 Trace |
| 事务回滚 | PASS | 注入失败后目标 Session 行数为 0 |
| Repository 越权攻击 | PASS | 详情、更新、删除、反馈等 5 类外部身份操作均返回 404 |
| HTTP 三账号攻击矩阵 | PASS | 同租户跨用户与跨租户泄漏 0；详情/更新/删除/反馈/Trace 404；请求体身份注入 422 |
| 浏览器多账号 | PASS | 用户 A 可见自己的会话；注销后同租户用户 B 历史会话为空；控制台 warning/error 0 |
| PostgreSQL 失败语义 | PASS | 不再以 JSON/fallback 成功响应；接口映射为 503 |
| Qdrant 安全探针 | PASS | TLS、无 Key 拒绝、只读 Key ACL、1024 维、strict mode、探针集合清理全部通过；Candidate 持久变更 0 |
| Python 目标回归 | PASS | 101 passed，17.44s |
| Python 编译 | PASS | `compileall` 通过 |
| 前端 TypeScript/Vite | PASS | 3675 modules，构建 1m11s |
| 一键启动闭环 | PASS | PostgreSQL/Redis/Qdrant/Celery/Backend/Frontend 全部健康；重复启动复用已健康服务 |
| 临时数据清理 | PASS | 3 个测试账号和所有 `day2_%` 记忆行均为 0 |
| 发布边界 | PASS | RAG-R1 仍为 candidate，`is_current=false`；未切换、未激活、未发布 |

## 证据

统一证据目录：`docs/codex/evidence/DAY2_MEMORY_SAFETY_PERSISTENCE_20260808_184725/`

关键文件：

- `01_schema_audit.json`
- `02_migration_replay_final/migration_replay.json`
- `03_memory_acceptance.json`
- `04_http_attack_matrix.json`
- `05_temporary_data_cleanup.txt`
- `06_residue_and_release_state.json`
- `07_pytest_101.txt`
- `08_compileall.txt`
- `09_frontend_build.txt`
- `10_browser_acceptance.md`
- `11_qdrant_runtime_probe.json`
- `12_run_project_precommit.txt`
- `13_run_project_postcommit_idempotent.txt`
- `14_launcher_contract_after_retry_fix.txt`

## 回滚方案

1. 代码回滚：将本次 Day2 提交整体 revert；不使用工作区强制重置。
2. 数据库回滚：使用迁移身份执行 `alembic downgrade 0018_rag_enterprise_r1`。该操作会移除 Day2 身份/幂等列和索引，执行前必须再次备份并确认业务停写。
3. 启动器回滚：代码 revert 后删除本地 JWT 文件不是必要步骤；该文件位于 `.codex_tmp` 且被 Git 忽略。若确需删除，应由用户确认后对该单一明确路径操作。
4. 检查点：`backups/phase3/20260808_174239329_DAY2_MEMORY_SAFETY_PRE/` 保存了任务前 Git 状态、diff、未跟踪清单、关键哈希、数据库影响说明与恢复说明。

## 已知情况与边界

- 一次扩大范围的探索性子集出现 3 项既有电价工具测试因本地数据资产不可用而失败；未修改断言或伪造通过，也未计入本次 101 项目标回归。Day2 目标回归随后独立执行并全部通过。
- 首轮尝试了仓库不存在的 `npm run typecheck`，npm 在系统默认缓存生成了一条日志；未产生项目变更。后续前端构建的 npm cache、TEMP 和 TMP 均固定到 RC 工作树的 E 盘忽略目录。
- 未执行 RAG alias 切换、模型 Candidate→Active、正式预测、生产数据库不可逆操作或生产发布。
