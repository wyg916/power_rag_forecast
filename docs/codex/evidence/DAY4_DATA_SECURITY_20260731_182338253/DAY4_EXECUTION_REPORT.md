# BETA10D Day 4 数据访问安全执行报告

## 1. 结论

- 最终结论：`PASS`。
- Day 4 已完成：数据访问面盘点、数据集白名单、未注册对象默认拒绝、任意 SQL 封禁、参数化查询、PostgreSQL 最小权限、迁移/运行/安全仓储身份分离、数据中心安全适配、注入与越权测试、真实角色 ACL 测试及 Day 3 RBAC 回归。
- Day 5 准入：`GO`；本轮未开始 Day 5，也未实施预测、报告真实性或其他后续范围。
- 正式 Alembic revision 未增加；单一 head 仍为 `0016_strategy_runtime`。

## 2. 干净工作区重建与准入

| 项目 | 结果 |
| --- | --- |
| 可信基线 | `45092b8b8f27b7af9a682d00eed48023651e46a0` |
| 新 worktree | `E:\智能运营分析项目_worktrees\beta10d_day4_data_security_v2` |
| 新分支 | `beta10d/day4-data-access-security-v2` |
| 初始 Git 状态 | tracked modified 0、staged 0、untracked 0 |
| RAG-R1 提交 | 0；未包含 `feat(rag): enforce tenant permission boundary` |
| 外部文件 | 无 `.env`、无 `backups/`、无 RAG Word |
| 检查点 | `E:\智能运营分析项目_备份\beta10d\20260731_174735975_DAY4_DATA_SECURITY_V2_PRE` |
| 初始结论 | `GO` |

基线最近提交为 `45092b8 docs(codex): close Day 3 RBAC evidence`、`b6a0c74 test(security): block RBAC tests from writing business schema`、`fb3cbd0 docs(codex): close Day 3 RBAC verification` 和 `911478c test(security): add Day 3 route and role gates`。完整初始 Git 状态、工作树列表、跟踪文件清单、数据库只读快照和 Schema-only dump 均保存在检查点。

Day 3 关键文件初始 SHA-256：

- 权限矩阵 CSV：`432dfca6147212fc1026182dc295e07c32c8566212fc2bc08ff2ae20bebd6b3b`
- 数据库隔离门禁：`3dac2a4163b6939e6ed002b4d7a7bfc615174fe0c6322c4e4dd5f22210bd6a61`
- 隔离测试：`740712f49144939b045dc2f9befd0a6eda76da3384ef404d72062cca84cde5b4`
- Day 3 报告：`461f72a29ae5c831f0d10d6b4cbba616263637d6bcf3a96b23e7e8ef7d953f4f`

Day 3 历史按事实保留：早期宽范围测试曾误写现有 `public`，随后经用户授权完成事务化精确恢复；Day 3 最终收口复验的 public 写入为 0。

## 3. 实施结果

### 3.1 数据访问面与白名单

- 共盘点 27 个 API、客户端、AI、仓储、脚本和测试访问面：12 个保留、11 个替换、4 个禁用。
- Day 4 前识别 11 个自由 SQL、动态对象或物理元数据高风险入口；最终公开业务 API 接收原始 SQL、Schema、物理对象名、原始列名、JOIN、子查询或函数的入口均为 0。
- `backend/app/data_registry.py` 成为唯一注册事实源，登记 11 个稳定 `dataset_id`；API 不返回物理对象名或原始列名。
- 未注册数据集、字段、过滤、排序和搜索默认拒绝；管理员不能绕过注册表。
- 访问面清单见 `docs/codex/security/DATA_ACCESS_SURFACE.csv` 和同目录说明文档。

### 3.2 任意 SQL 封禁与参数化查询

- 旧 `/api/data/tables*` 动态对象接口已移除并返回 404。
- `POST /api/data/sql/query` 对任意请求体和任意角色固定返回 410；请求体不解析、不记录 SQL，也不创建数据库连接。
- 行查询由静态 SQLAlchemy Core `Table`/`Column` 映射生成；值全部绑定参数，字段、方向和策略来自注册表枚举。
- 查询页大小、导出上限和超时由服务端强制限制；异常响应不回显 SQL、对象路径或连接信息。
- 市场仓储只允许 11 个精确对象策略；电价 AI 工具只允许 5 个固定查询模板，未知组合在接触数据库前拒绝。

### 3.3 AI 与前端适配

- AI 业务查询改为受控 `dataset_id`、公开字段和有限意图；任意 SQL 服务保留为先拒绝兼容层。
- 数据中心、数据目录和 AI 客户端不再传递物理表名或 SQL；稳定展示业务数据集 ID、分页、过滤和安全导出状态。
- 真实浏览器在 1366×768 与 1920×1080 下均无水平溢出，无 `raw_*`、`users`、`audit_logs` 或“SQL 查询”暴露，控制台 warning/error 为 0。

### 3.4 数据库身份与 ACL

- 普通运行组/登录：`beta10d_app_runtime`（NOLOGIN）/`beta10d_app_login`（LOGIN）。
- 安全仓储组/登录：`beta10d_security_runtime`（NOLOGIN）/`beta10d_security_login`（LOGIN）。
- 四个角色均为 NOSUPERUSER、NOCREATEDB、NOCREATEROLE、NOREPLICATION、NOBYPASSRLS；登录角色无数据库 CREATE 和 `public` Schema CREATE。
- 普通运行身份仅可读注册业务对象，并可写受控业务对象；对审计表仅允许不依赖序列的 INSERT，不得读取 `users`、`audit_logs`、`alembic_version`、`pg_authid`，不得服务端读文件、建 Schema 或建角色。
- 安全仓储身份仅访问认证、配置和审计对象，不得读取业务数据。
- 迁移继续使用显式 `MIGRATION_DATABASE_URL` 维护身份，不回退到普通运行身份；Compose 的 bootstrap、backend 和 worker 身份已分离，`AUTO_MIGRATE=0`。
- 正式本地连接仅保存在 Git ignore 的 `E:\智能运营分析项目_本地配置\beta10d_day4_runtime.env`，未输出或提交密码、Token、API Key。

## 4. 数据库前后指纹

正式角色与 ACL 复验结果见 `DATABASE_ROLE_AND_FINGERPRINT_GATE.json`：

| 指标 | 前 | 后 |
| --- | ---: | ---: |
| public 表 | 62 | 62 |
| public 视图 | 8 | 8 |
| public 序列 | 47 | 47 |
| public 函数 | 37 | 37 |
| Alembic head | `0016_strategy_runtime` | `0016_strategy_runtime` |
| 结构 SHA-256 | `9610393a5c8a626f3cea41c534145402a789bbe7cf68741c4869ed329827cf02` | 同前 |
| 内容变化表 | 0 | 0 |
| 状态变化序列 | 0 | 0 |

真实允许项和拒绝项均 PASS：注册数据集 SELECT、受控业务 UPDATE/DELETE 事务回滚、无序列审计 INSERT 事务回滚、安全仓储认证/审计读取允许；普通身份读取敏感对象/系统目录、服务端文件、DDL、建角色以及安全身份读取业务数据均返回 `InsufficientPrivilege`。

### 4.1 门禁发现与精确恢复记录

2026-07-31 19:45 的一次 91 项隔离复跑中，普通仓储已经位于一次性 Schema，但安全仓储仍继承正式身份，产生 7 条 `ai.debug_view` 测试审计记录（`audit_logs.id` 39–45）并使 `audit_logs_id_seq` 从 38 前进到 45。pytest 为 91/91，但 public 指纹门禁主动给出 FAIL。

处置过程：先只读核对 7 行的 ID、actor、action、resource type、status 和序列状态；仅在总行数 45、ID 39–45 全部属于本次测试且序列为 45 的精确前置条件下，在单一事务中删除 7 行并把序列恢复为 38/`is_called=true`。恢复后行数 38、内容 MD5 `8c2a47b88f4149ea686a550b451165bb` 与门禁前一致。随后修正 Day 3 门禁，使普通和安全仓储均使用一次性 NOLOGIN 角色及隔离 Schema，并清空测试进程的迁移身份；91 项和完整 268 项均重新 PASS，public 前后完全一致。该事件未改写为“测试期间从未写入数据库”。

## 5. 验证结果

| 门禁 | 结果 |
| --- | --- |
| Day 3 定义回归 + Day 4 增量，隔离 PostgreSQL | 268 passed，0 failed，public match，临时 Schema/角色残留 0 |
| Day 4/SQL/RBAC/AI 专项，修复后隔离复跑 | 91 passed，0 failed，public match，临时 Schema/角色残留 0 |
| 正式 runtime/security 角色与 ACL | PASS，11 个注册数据集验证通过 |
| API 权限矩阵 | 195 方法+路径、183 唯一路径、7 公开、188 受保护；未分类/未保护业务路由 0 |
| Node 状态测试 | 7 passed |
| TypeScript + Vite production build | PASS，3675 modules |
| Python compileall | PASS |
| 主 Compose / enterprise Compose | 均解析 PASS |
| 浏览器数据中心 | PASS；两档分辨率无溢出、敏感对象名 0、console warning/error 0 |
| `git diff --check` | PASS |
| 高置信敏感信息扫描 | 0 命中；`.env`、备份和 RAG Word 跟踪文件 0 |

证据：

- 完整隔离回归：`E:\智能运营分析项目_验证\beta10d_day4_day3_regression_postcommit_v2_20260731.json`
- 专项隔离回归：`E:\智能运营分析项目_验证\beta10d_day4_postcommit_targeted_v2_20260731.json`
- 浏览器：`E:\智能运营分析项目_验证\beta10d_day4_browser_20260731_194000.json`
- 正式 ACL/指纹：本目录 `DATABASE_ROLE_AND_FINGERPRINT_GATE.json`

补充诊断：本轮早期曾执行仓库全历史无选择 pytest，结果为 425 passed、23 failed、30 skipped、46 errors；主要为历史外部/RAG/静态契约以及旧 monkeypatch 仓储连接缝隙，不是 Day 3 定义的 252 项测试门禁。已修复与 Day 4 身份分离直接相关的仓储连接缝隙并定向通过 23/23；最终以 Day 3 定义文件集加 Day 4 增量形成的 268/268 隔离门禁作为本任务验收，不把早期全历史诊断伪报为全绿。

## 6. 提交与修改范围

收口前原子提交：

1. `3eaaf572efc5505b287d8f5d6b75819cdb82fbf0` — 数据访问面与唯一注册表。
2. `67655c8367e899b7c5cf755c74d54ec6a78e6e88` — 注册数据集 API 与参数化查询。
3. `027e1c3bc9f938c13ee343e216dea5797666817a` — AI 任意查询替换。
4. `5d4b73a935e20412e85e395aa3db30b677c45f30` — 数据库身份、ACL、Compose 与门禁。
5. `7359dd53d29bf1b62dc3f17a0c95e8b964434f18` — 前端数据中心安全契约。
6. `4254dc650cbe03ef7454a09860b872671f5c99cb` — Day 4 安全测试与权限矩阵。
7. `11a239b8b3e9f8d6cfde8820a730b26b24a529f3` — 安全仓储测试隔离修复。
8. 本报告、任务状态、并行登记和证据位于最终收口提交。

最终交付共 56 个跟踪文件，按范围为：2 个公共环境模板、22 个 backend 文件、2 个 Compose 文件、5 个 frontend 文件、1 个迁移环境文件、4 个安全脚本、10 个测试文件和 10 个任务/安全/证据文档。`alembic/versions/**` 修改为 0。

## 7. RAG-R1 隔离与并行集成

- 受保护路径：`E:\智能运营分析项目_worktrees\beta10d_day4_data_security`，分支 `beta10d/day4-data-access-security`。
- 检查点 HEAD 为 `6c10ae734cb2e24b4936a53f7d6bf6f57def7a79`；2026-07-31 19:56 只读复核时，外部流程已推进至 `5ed3847903e802231560ceab2f277711bc824eeb`，工作树仍干净。
- 7 个关键哈希中 6 个与检查点完全一致；`docs/codex/tasks/08_RAG_ENTERPRISE_R1.md` 随外部 RAG 提交变化。Day 4 未修改、reset、clean、revert、rebase、stash、删除、merge、cherry-pick 或复制该工作树。
- `codex/rag-enterprise-ingestion` 与 `codex/rag-enterprise-runtime` 未收到合规交付清单，本轮均未检查和集成；冲突仅登记，不提前处理 RAG/Day 8 范围。
- 详细快照见本目录 `RAG_WORKTREE_PROTECTION_AFTER.json` 和 `docs/codex/PARALLEL_INTEGRATION_REGISTER.md`。

## 8. 回滚

- 代码：从最终收口提交开始逆序执行逐笔 `git revert`；不使用 reset、clean、rebase 或强制改写。
- 数据：本任务无正式 Schema/业务数据迁移；检查点保存 `database_before.json`、Schema-only dump 及哈希。若撤回 ACL，先停止服务，再由维护身份按 `scripts/day4_apply_database_security.py` 的精确对象清单撤销 `beta10d_` 角色授权，并以正式角色门禁复验；不得使用 `GRANT/REVOKE ALL` 或批量对象操作。
- 配置：停止服务后移除或替换项目盘外的本地连接文件；公共模板不含真实凭据。
- 恢复后必须重新执行权限矩阵、正式 ACL、public 指纹、268 项隔离回归和前端构建。

## 9. 剩余风险与下一步

- 全历史无选择 pytest 尚包含与 Day 4 门禁无关的既有外部/RAG/旧静态契约失败，已如实记录；进入后续跨支线总集成前应由对应所有者提供合规交付清单并重新建立全仓门禁。
- 迁移身份仍为显式维护连接，不创建新的长期迁移登录角色；其凭据轮换和托管属于部署运维，不在 Day 4 代码库内保存。
- Day 5 准入结论为 `GO`，但必须由用户另行明确启动；本报告未开始 Day 5。
