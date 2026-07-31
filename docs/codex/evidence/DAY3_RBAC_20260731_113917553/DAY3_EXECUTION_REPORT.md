# Day 3 业务 API 认证与 RBAC 权限全面封口执行报告

## 1. 结论

- 结论：**CONDITIONAL PASS**。
- Day 3 技术门禁全部通过：API 路由清单闭合、业务接口默认认证、权限矩阵闭合、401/403 语义区分、生产文档端点关闭、前端权限门控、下载与 SSE/兼容别名封口、定向回归、构建和数据库恢复后终检均通过。
- 条件项仅来自 Day 3 执行期间出现的外部工作树漂移：`AGENTS.md`、`docs/codex/MASTER_ENGINEERING_RULES.md`、`docs/codex/TASK_STATUS.md` 中的 `GLOBAL-DATA-PRESENTATION` 行，以及未跟踪的 `RAG/企业知识库_知识体系与企业级开发实施指南_v1.0.docx`。这些内容未纳入 Day 3 提交，未删除、覆盖或移动。
- 因最终工作树不能证明全局干净，**不得据此自动进入 Day 4**；需由用户先确认并处理或提交上述外部漂移。
- 本轮未实施 Day 4 的数据浏览白名单、任意 SQL 改造及任何后续 Day 内容。

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

本任务修改 20 个文件，未超过门禁：

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

外部漂移文件不计入 Day 3 修改清单，也不进入 Day 3 提交。

## 9. 原子提交

1. `8c1882e0f5cd32ff5240d3dcebf0dea53a77d68c` — `feat(security): inventory and classify all API routes`
2. `f13f4d916a40567d3fc60577570fd88d7f0a8d5a` — `feat(security): enforce fail-closed API authorization`
3. `5bf54757bdc07d41cc697773824ad7c2b2d89afc` — `fix(frontend): align auth and privileged actions with RBAC`
4. `911478cbc64cd121066439e2380d17689ab91daf` — `test(security): add Day 3 route and role gates`
5. 本报告与 `TASK_STATUS.md` 所在收口提交 — `docs(codex): close Day 3 RBAC verification`

## 10. 回滚

- 代码与文档：按上述提交逆序执行 `git revert <commit>`；禁止使用 `git reset --hard` 或 `git clean`。
- 数据库：Day 3 最终逻辑内容已恢复到前快照，回滚代码无需再改数据库。恢复包只用于审计或在确认目标状态后重放，不得无确认执行。
- 配置：生产文档端点、认证默认值和权限矩阵均随原子提交回滚。
- 外部漂移：由其产生者单独处理；Day 3 不提供删除、覆盖或回退操作。

## 11. 已知问题与 Day 4 准入

- 12 个宽范围历史测试失败未在 Day 3 越界修复；需按其所属任务日另行处理。
- 当前工作树保留三项已跟踪外部规则/状态漂移和一个未跟踪 RAG Word 文件，故全局 clean-tree 门禁未满足。
- Day 3 技术能力已闭合，但在用户确认外部漂移归属并使工作树达到可审计状态前，Day 4 准入为 **NO-GO**。
