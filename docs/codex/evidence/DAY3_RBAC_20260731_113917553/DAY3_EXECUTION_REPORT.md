# Day 3 业务 API 认证与 RBAC 权限全面封口执行报告

## 1. 结论

- 结论：**PASS**。
- Day 3 技术门禁继续通过：195 个方法+路径全部归类，7 个明确公开端点、188 个受保护端点，未分类和未保护业务路由均为 0。
- 原 `CONDITIONAL PASS` 条件已经闭合：Pytest 默认不再继承仓库本地业务数据库；所有数据库集成回归改由一次性受限 Schema/NOLOGIN 角色执行，并自动验证 `public` 前后内容、结构、序列和 Alembic 版本。
- 本次隔离复验期间 `public` 写入为 0，临时 Schema 和角色残留为 0；Day 3 安全与相关业务回归、Node、TypeScript、Vite、Python 编译和敏感信息扫描全部通过。
- Day 3 执行早期曾向现有数据库产生测试写入、随后经用户授权精确恢复的事实继续完整保留，绝不改写为“测试期间从未写入”。
- 外部工作树漂移均按文件/hunk 归属隔离，未删除、覆盖、stash 或混入 Day 3 提交。Day 4 独立 worktree 从本报告所在最终 HEAD 创建并保持干净，因此 Day 4 准入为 **GO**。
- 本轮仅创建 Day 4 分支和 worktree，未实施数据浏览白名单、任意 SQL 改造及任何 Day 4 业务内容。

## 2. 基线与检查点

- 项目目录：`E:\智能运营分析项目`
- 起始分支：`beta10d/day2-reproducible-environment`
- 起始 HEAD：`bfb536fdc9a164b40103fc114278c47ac6d96a30`
- Day 3 分支：`beta10d/day3-rbac-closure`
- 起始工作树：干净
- Day 3 前检查点：`E:\智能运营分析项目_备份\beta10d\20260731_113917553_DAY3_RBAC_PRE`
- 验证证据根：`E:\智能运营分析项目_验证\beta10d_day3_20260731_113917553`
- 起始数据库：public 62 张表，Alembic 单一 head `0016_strategy_runtime`，结构 SHA-256 `96b27b594f5c69977f6f7faf769b5fce4b20d75af77581b6df74c80199cb3ce4`。

## 3. 路由盘点与权限矩阵

- FastAPI 方法+路径：195。
- 唯一路径：183。
- 方法分布：GET 129、POST 57、PUT 5、DELETE 3、PATCH 1。
- 风险分布：public 7、business 99、sensitive 58、admin 31。
- 保护路由：188；写操作 66，其中除登录外的 65 个写路由全部受保护。
- 改造前路由级 guard 为空：60；剔除 7 个公开端点后需封口的业务路由：53。
- 改造后目标未分类业务路由：0；受保护写路由缺少权限：0。
- 公开白名单仅包含：
  - `POST /api/auth/login`
  - `GET /api/health`
  - `GET /health`
  - 仅开发环境可用的 `GET /docs`
  - 仅开发环境可用的 `GET /docs/oauth2-redirect`
  - 仅开发环境可用的 `GET /openapi.json`
  - 仅开发环境可用的 `GET /redoc`
- 机器可读矩阵：`docs/codex/security/API_PERMISSION_MATRIX.csv`
- 人工复核矩阵：`docs/codex/security/API_PERMISSION_MATRIX.md`
- 生成与漂移检查：`python scripts/day3_generate_permission_matrix.py` 及 `--check` 均通过；矩阵包含 Method、Path、Module、Handler、Route Name、Response Model、风险、当前/目标 guard、权限、允许角色、匿名、写操作、前端消费者和备注。

## 4. 认证与 RBAC 封口

- 新增中央 `ApiSecurityMiddleware`，以矩阵为运行时事实源；应用启动时校验实际路由与矩阵完全一致，未知业务路由 fail-closed。
- 生产环境关闭 Swagger、ReDoc 和 OpenAPI 文档端点。
- 未认证、无效/过期/信息不完整 token、停用用户统一返回 401，并携带 `WWW-Authenticate: Bearer`。
- 已认证但权限不足统一返回 403，不再与 401 混淆。
- 删除匿名 `dev_admin` 回退；开发身份头只允许在认证关闭且 `development`/`test` 环境使用，生产环境禁止。
- 未知角色不再静默回退到 Viewer，权限集合为空。
- Admin 保留全权限；Analyst 可进行分析、预测、数据、报告、知识和策略业务操作，但不能执行高风险模型管理、任务管理、用户管理或系统配置；Developer 保留诊断、调试、审计、追踪和只读运维能力；Viewer 仅保留受限只读业务视图；Reviewer 仅保留审阅相关能力。
- CORS 中间件保持在安全中间件外层，401/403 响应仍满足浏览器跨域契约。
- 已覆盖报告下载、知识库导出、数据导出、AI SSE `/api/ai/chat/stream`，以及模型 backtest、feature-schema、leakage-check 的单复数兼容别名，未发现旁路。

## 5. 前端闭环

- 前端认证默认开启，不再依赖构建环境显式设置才启用。
- 401 清理本地认证态并回到登录页，同时保留原目标路由；403 显示“无权访问”，不误跳登录页。
- 报告下载改为认证请求，并保留服务端 `Content-Disposition` 文件名。
- 报告生成/复核/删除、模型管理和任务管理按钮按权限显示和禁用。
- 浏览器 mock 验证覆盖 1366×768 与 1920×1080：
  - 匿名访问业务路由进入登录页；
  - 登录后返回原目标页；
  - 401 清 token、回登录并保留目标；
  - 403 显示无权访问且不跳登录；
  - 浏览器控制台错误 0。

## 6. 测试与构建

- 2026-07-31 Day 3 收口隔离复验：252 passed、0 failed、0 skipped、0 deselected；全部在 `beta10d_day3_close_` 一次性 Schema 中执行。
- 当前代码态隔离门禁自测：6 passed；受限角色对 `public.audit_logs` 的实际写入探针被 PostgreSQL 拒绝。
- 隔离复验期间 `public` 前后全部表内容指纹、序列状态、结构清单与 Alembic head 一致；临时 Schema/角色清理后残留均为 0。
- 权限矩阵生成与 `--check`：PASS，195 个方法+路径、183 个唯一路径、7 个公开、188 个受保护。
- `tests/test_day3_api_security.py`：48 passed。
- `tests/test_t004_security.py tests/test_auth_rbac.py tests/test_ai_debug_permission.py`：24 passed。
- Day 3 相关安全回归：213 passed、1 个受控 seed 用例 deselected。
- Python 语法编译：PASS。
- Node viewState：7 passed、0 failed。
- TypeScript `npx.cmd tsc --noEmit`：PASS。
- Vite 构建：PASS，3675 modules，33.11s。第一次独立构建在 transforming 阶段超时，无编译错误；随后独立重试通过。
- 早期宽范围历史测试结果为 465 passed、12 failed、30 skipped、1 deselected。12 个失败集中在既有前端静态契约、RAG/Phase5 隔离集成、启动脚本换行和 tariff 证据契约，不作为 Day 3 技术门禁通过依据；其日志被完整保留。
- 关键日志位于 `E:\智能运营分析项目_验证\beta10d_day3_20260731_113917553\logs`，包括：
  - `permission_matrix_check_with_inventory_fields.log`
  - `pytest_day3_security_inventory_final.log`
  - `pytest_security_regression_final.log`
  - `pytest_day3_relevant_regression_final.log`
  - `node_viewstate_final.log`
  - `vite_build_final_retry.log`
  - `pytest_full_nonwriting.log`

## 7. 数据库写入事件、恢复与终检

- Day 3 不包含数据库结构或业务数据变更；未执行迁移、seed、全表更新或删除。
- 早期宽范围历史测试误连接当前 public 数据库，产生了可识别的测试写入和时间戳更新。发现后立即停止写入测试并向用户披露；未经授权未执行恢复。
- 用户明确确认数据库恢复后，生成恢复包并进行事务化恢复。首轮恢复因 `task_logs` 指纹不一致自动回滚，未改变数据或序列；补充识别 ID 10、14 的原有行更新时间后，第二轮单事务恢复成功：
  - 删除 49 条测试 `audit_logs`；
  - 删除 33 条测试 `ai_traces`；
  - 删除 17 条测试 `task_logs`；
  - 恢复 `task_logs` ID 10、14；
  - 恢复 2 条 `storage_devices`、48 条 `storage_soc_snapshots`、6 条 `strategy_execution_items`、2 条 `task_runs` 的原值；
  - 恢复 `audit_logs_id_seq=38`、`task_logs_id_seq=71`。
- 有效恢复包：`E:\智能运营分析项目_验证\beta10d_day3_20260731_113917553\unexpected_public_test_writes_recovery_package_v2.json`
- 恢复包 SHA-256：`5afdacaa614fd1def01fb79ec0af3431ead5f85b90dab25600e1dc6c0a2bf8ee`。
- 最终只读复核：public 62/62 张表内容指纹与 Day 3 前快照完全一致，差异 0；Alembic 单一 head 为 `0016_strategy_runtime`；两条序列为 38/71。
- 最终证据：`E:\智能运营分析项目_验证\beta10d_day3_20260731_113917553\final_database_verification_after_commit_tests.json`
- 最终证据文件 SHA-256：`a5af1854e294689c542633ed45ee52d09940ef2bf5a58b8706769abada1abab7`
- 结论应表述为“发生过测试写入且已精确恢复，最终逻辑内容净漂移为 0”，不得表述为“执行期间从未写入数据库”。物理 WAL/heap 变化不属于逻辑内容恢复范围。

## 8. 修改文件

Day 3 全周期共修改 22 个文件；本次收口增量仅涉及 3 个测试门禁文件、1 个报告和 `TASK_STATUS.md` 的 Day 3 hunk。有效代码增量不超过 1000 行门禁：

1. `backend/app/core/api_security.py`
2. `scripts/day3_generate_permission_matrix.py`
3. `docs/codex/security/API_PERMISSION_MATRIX.csv`
4. `docs/codex/security/API_PERMISSION_MATRIX.md`
5. `backend/app/core/security.py`
6. `backend/app/main.py`
7. `backend/app/api/v1/endpoints/report.py`
8. `frontend/src/context/AuthContext.tsx`
9. `frontend/src/api.ts`
10. `frontend/src/pages/model/ModelCenterPage.tsx`
11. `frontend/src/pages/report/ReportCenterPage.tsx`
12. `frontend/src/pages/task/TaskCenterPage.tsx`
13. `pytest.ini`
14. `tests/conftest.py`
15. `tests/test_ai_debug_permission.py`
16. `tests/test_auth_rbac.py`
17. `tests/test_t004_security.py`
18. `tests/test_day3_api_security.py`
19. `docs/codex/TASK_STATUS.md`
20. `docs/codex/evidence/DAY3_RBAC_20260731_113917553/DAY3_EXECUTION_REPORT.md`
21. `scripts/day3_test_database_guard.py`
22. `tests/test_day3_database_isolation.py`

外部漂移文件不计入 Day 3 修改清单，也不进入 Day 3 提交。

## 9. 原子提交

1. `8c1882e0f5cd32ff5240d3dcebf0dea53a77d68c` — `feat(security): inventory and classify all API routes`
2. `f13f4d916a40567d3fc60577570fd88d7f0a8d5a` — `feat(security): enforce fail-closed API authorization`
3. `5bf54757bdc07d41cc697773824ad7c2b2d89afc` — `fix(frontend): align auth and privileged actions with RBAC`
4. `911478cbc64cd121066439e2380d17689ab91daf` — `test(security): add Day 3 route and role gates`
5. `fb3cbd0e2790599c73d2865384e012788ce503cf` — `docs(codex): close Day 3 RBAC verification`
6. `b6a0c746c56a61156dfa1abe8bc3a553b6b4734d` — `test(security): block RBAC tests from writing business schema`
7. 本报告与 `TASK_STATUS.md` Day 3 hunk 所在最终收口提交 — `docs(codex): close Day 3 RBAC evidence`

## 10. 回滚

- 代码与文档：按上述提交逆序执行 `git revert <commit>`；禁止使用 `git reset --hard` 或 `git clean`。
- 数据库：Day 3 最终逻辑内容已恢复到前快照，回滚代码无需再改数据库。恢复包只用于审计或在确认目标状态后重放，不得无确认执行。
- 隔离门禁：如需回滚本次门禁，仅 `git revert b6a0c746c56a61156dfa1abe8bc3a553b6b4734d`；该提交不包含数据库迁移。若进程异常中断，只允许核验并删除名称以 `beta10d_day3_close_` 开头且所有者与同名前缀角色精确匹配的临时 Schema/角色，不得操作 `public`。
- 配置：生产文档端点、认证默认值和权限矩阵均随原子提交回滚。
- 外部漂移：由其产生者单独处理；Day 3 不提供删除、覆盖或回退操作。

## 11. 已知问题与 Day 4 准入

- 早期宽范围历史套件中的 12 个非 Day 3 失败仍按所属任务日处理；本次没有越界修复，也没有用 deselect 跳过 Day 3 验收。
- 原工作区继续保留外部规则/状态漂移、RAG Word 和并行任务 `backups/`；这些内容不影响从 Day 3 最终提交创建全新干净 worktree。
- Day 4 分支：`beta10d/day4-data-access-security`。
- Day 4 worktree：`E:\智能运营分析项目_worktrees\beta10d_day4_data_security`。
- Day 4 worktree HEAD 与本报告所在 Day 3 最终提交一致；tracked modified、staged、untracked 均为 0，未复制 `.env`、RAG Word 或原工作区外部漂移。
- Day 3 最终结论：**PASS**；Day 4 准入：**GO**。

## 12. 收口补充证据

### 12.1 外部工作区归属

| 文件/目录 | 状态 | 与 Day 3 关系 | 处理结论 |
| --- | --- | --- | --- |
| `AGENTS.md` | tracked modified | 否；`GLOBAL-DATA-PRESENTATION` 并行规则 | 保留原地，未暂存/提交 |
| `docs/codex/MASTER_ENGINEERING_RULES.md` | tracked modified | 否；`GLOBAL-DATA-PRESENTATION` 并行规则 | 保留原地，未暂存/提交 |
| `docs/codex/TASK_STATUS.md` | tracked modified | 部分相关 | 仅暂存本行 Day 3 hunk；`GLOBAL-DATA-PRESENTATION` hunk 保留原地 |
| `RAG企业知识库_知识体系与企业级开发实施指南_v1.0.docx` | untracked | 否；用户输入附件 | 保留原地，不进入 Git |
| `backups/phase3/20260731_154414_RAG_ENTERPRISE_PRE` | untracked | 否；并行 RAG 任务检查点 | 保留原地，不进入 Git |

原始复核哈希：

- `AGENTS.md`：`6eecac8421afabe81123a9604169c99f779b3ef35d9cbe3dfcce37f4d7c4d96c`
- `docs/codex/MASTER_ENGINEERING_RULES.md`：`7a95bc0d58d22194ef99c91efaac752f1c04e3e6b0f52cd10fdab398a6970140`
- `docs/codex/TASK_STATUS.md`（收口修改前全文件）：`20fbe77848cd984c7f2af59c12c21da1736e786da2de42c4094298e718a5fa7b`；其中外部 `GLOBAL-DATA-PRESENTATION` diff 保持不变，仅追加本报告授权的 Day 3 hunk。
- RAG Word：`538dec927a9c87d1558645f805564993aa4697f41c03f8182674682e2b365482`
- 并行 RAG 检查点：17 个文件、1,231,441 bytes，清单 SHA-256 `91184627d5e14aa8056069399cf59deacb96982fdc98083de5faafefa47e31f8`。

### 12.2 写入根因与具体对象

- 根因是旧 `tests/conftest.py` 在导入应用前没有覆盖仓库 `.env` 中的本地 `DATABASE_URL`；身份 override 只替换认证主体，没有隔离数据库连接。未自行 monkeypatch 数据库的测试因而复用全局/缓存 PostgreSQL engine 并连接到现有 `public`。
- 当时没有服务端受限角色、隔离 `search_path`、Schema 前缀校验或前后内容/序列监测；个别测试清空 `DATABASE_URL` 的做法不是全局门禁，因此未能阻止写入。
- 定位到的具体写入入口包括任务创建/重试/取消和 Celery 状态测试（`tests/test_task_api.py`、`tests/test_celery_task_status.py`、P4 任务生命周期相关测试），AI/Web 对话与调试测试，以及 `tests/test_p6_p1_3c_strategy_runtime.py::test_controlled_seed_is_idempotent_and_traceable`。
- 对象包括 `audit_logs`、`ai_traces`、`task_logs`、`task_runs`、`storage_devices`、`storage_soc_snapshots`、`strategy_execution_items` 及 `audit_logs_id_seq`、`task_logs_id_seq`。第 7 节记录的授权精确恢复事实保持不变。

### 12.3 自动化隔离门禁

- 普通 Pytest 启动会在应用导入前清空继承的本地 `DATABASE_URL`，设置会话只读兜底；需要数据库的测试必须经 `scripts/day3_test_database_guard.py`。
- runner 只接受 `localhost/127.0.0.1/::1:5432/postgres` 与 `postgres` 启动身份，创建唯一 `beta10d_day3_close_` Schema 和同名前缀 `NOLOGIN/NOINHERIT` 角色。
- Alembic 迁移表位于隔离 Schema，迁移到单一 head `0016_strategy_runtime` 后再运行测试；运行时校验 `current_user`、`current_schema`、`search_path`、Schema owner 和 `public` 写权限。
- 受限角色没有 `public` CREATE、审计表 DML 或审计序列写权限；测试使用固定时间、固定 run_id、明确 `controlled_test_fixture` 来源的合成 fixture，不读取或修改真实业务记录。
- runner 对 `public` 全表内容指纹、序列状态、结构清单和 Alembic head 做前后对比；只有精确名称前缀且 owner 匹配时才清理临时 Schema/角色，随后复核残留为 0。

### 12.4 隔离复验与数据库终态

- 收口检查点：`E:\智能运营分析项目_备份\beta10d\20260731_153945424_DAY3_CLOSURE_PRE`
- 收口验证根：`E:\智能运营分析项目_验证\beta10d_day3_closure_20260731_153945424`
- 最终 Python 隔离回归：252 passed、0 failed、0 skipped、0 deselected。
- 合成 fixture 仅写隔离 Schema：`forecast_runs` 1 行，`forecast_results`、`raw_market`、`raw_load`、`raw_weather` 各 24 行。
- 测试自身仅写隔离 Schema：`ai_traces` 2、`audit_logs` 8、`storage_devices` 2、`storage_soc_snapshots` 48、`strategy_execution_items` 6、`task_logs` 13、`task_runs` 2；隔离序列推进到 audit 8、task log 13。
- 测试结束后上述 Schema 整体清理；最终 `beta10d_day3_close_` Schema 0、角色 0。
- `public` 收口前后均为 62 张表、8 个视图、47 个序列、37 个函数，Alembic 单一 head `0016_strategy_runtime`。
- `public` 结构 SHA-256 前后均为 `9610393a5c8a626f3cea41c534145402a789bbe7cf68741c4869ed329827cf02`；全部表内容指纹和序列状态逐项相同，本次复验 `public` 写入为 0。
- 最终数据库证据：`E:\智能运营分析项目_验证\beta10d_day3_closure_20260731_153945424\public_database_final.json`，SHA-256 `e90fad7486f26609c7a6945b67bed8a7e6d147bd22e94ca65749c08f6efb930a`。
- 首次当前态门禁复核因外层日志管道 120 秒超时使子进程返回 120；该次 `public_match=true`、清理 PASS。去除管道并增加外层超时后，同一当前代码态 6/6 通过。
- Node 7/7、TypeScript `--noEmit`、Vite 正式构建、Python compileall 和权限矩阵 `--check` 均通过；高置信敏感信息扫描 0 命中。
