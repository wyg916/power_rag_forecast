# Day 6C 数据谱系恢复、真实输入补齐与候选模型质量修复报告

## 1. 正式结论

- `DAY6C NOT PASS`
- 阶段一：`NOT PASS`
- 阶段二至阶段五：`NOT EXECUTED`（阶段一停止条件触发）
- `ACTIVE SWITCH REQUEST: NO`
- `ACTIVE SWITCH EXECUTED: NO`
- `DAY6A REENTRY: NO`
- `ORIGINAL DAY6 ADMISSION: NO`
- `DAY7 ADMISSION: NO`

受限 PostgreSQL 身份已经恢复，角色身份、危险属性、Day 4 白名单读取和禁止访问均可复现；但阶段一整体仍失败：运行角色固有拥有多张正式业务表的写 ACL，且冻结训练快照无法由当前 PostgreSQL 的允许列完整复现。按任务书停止条件，本轮立即停止，不执行数据采集、Provider、模型根因分析、候选改进或质量验收。

## 2. Worktree、分支、HEAD 与 Git 状态

- worktree：`E:\智能运营分析项目_worktrees\beta10d_day6c_lineage_data_model_recovery`
- branch：`beta10d/day6c-lineage-data-model-recovery`
- 基线 HEAD：`55c2c53d8597530023947811ecfa7ebc4027c475`
- 基线 Git 状态：clean
- 收口提交：本文件所在提交
- 预检查点：`E:\智能运营分析项目_备份\beta10d\20260801_190147176_DAY6C_PRE_SANITIZED`
- 检查点清单：11 项，SHA-256 复算错误 0，敏感模式命中 0
- 先前脚本失败产生的部分目录：`E:\智能运营分析项目_备份\beta10d\20260801_185935058_DAY6C_PRE`；未删除、未作为正式基线使用。

## 3. 基线核验

- Day 6A：`beta10d/day6a-forecast-input-pipeline` / `669436d9573c1e81466fe6faed84b63f658489a0` / clean。
- Day 6B：`beta10d/day6b-online-safe-model` / `55c2c53d8597530023947811ecfa7ebc4027c475` / clean。
- RAG Ingestion：`codex/rag-enterprise-ingestion` / `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227` / clean。
- RAG Runtime：`codex/rag-enterprise-runtime` / `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d` / clean。
- 旧 RAG-R1：`beta10d/day4-data-access-security` / `7eaf8d3152f8ffe5bd983068a99145c9693b4925` / clean。
- RAG merge、cherry-pick、文件复制和数据库写入：0。

## 4. Active 与 Day 6B Candidate

Active 静态基线：

- model version：`model_20260620_063015`
- feature version：`features_140db8af25f9`
- schema hash：`a855692756793862b1fcfd3c68c701d1ad231b32e6581797d74f4a8ab4199281`
- registry artifact hash：`f6689b533cb8fc94e18ac53a399e9bac5a4f6fb4c4df354c701182fe23c70f59`
- artifact component hashes：已静态计算；未反序列化、未覆盖。
- 170 项名称/顺序与 Day 6A matrix 精确一致；artifact dtype 为 170 项 `numeric`。
- 训练：2024-07-13 06:00 至 2026-04-18 23:00；验证：2026-04-19 00:00 至 2026-05-18 23:00；测试：2026-05-19 00:00 至 2026-06-17 23:00。

Day 6B Candidate 静态基线：

- model version：`model_day6b_20260801_181807`
- feature version：`features_online_safe_289a51530a13`
- feature count：52
- model SHA-256：`104b64781fe17d36cfdd96349f78055d84408c6179b4b1b065161eb1e1371c60`
- 状态：未注册、未激活、未替换 Active。

## 5. 修改文件

Tracked：

- `docs/codex/day6c/DAY6C_EXECUTION_REPORT.md`
- `docs/codex/TASK_STATUS.md`
- `docs/codex/PARALLEL_INTEGRATION_REGISTER.md`

本地证据目录（由 `.gitignore` 排除）：

- `docs/codex/evidence/DAY6C_20260801_190147176/`

未修改代码、迁移、配置模板、Active artifact、Candidate artifact 或 RAG 文件。

## 6. 实际执行命令

核心命令如下；连接值始终由外部本地安全配置在进程内部读取，未出现在命令参数、报告或日志：

```powershell
git -C <worktree> rev-parse --abbrev-ref HEAD
git -C <worktree> rev-parse HEAD
git -C <worktree> status --porcelain=v1
git worktree add -b beta10d/day6c-lineage-data-model-recovery <day6c-worktree> 55c2c53d8597530023947811ecfa7ebc4027c475

E:\智能运营分析项目\.venv\Scripts\python.exe -B <phase1-gate-script> `
  --repo <day6c-worktree> `
  --secure-config E:\智能运营分析项目_本地配置\beta10d_day4_runtime.env `
  --output <phase1-evidence-json>

E:\智能运营分析项目\.venv\Scripts\python.exe -B <snapshot-reconcile-script> `
  --secure-config E:\智能运营分析项目_本地配置\beta10d_day4_runtime.env `
  --snapshot E:\智能运营分析项目\output\master_table.xlsx `
  --candidate-features <candidate-feature-cols> `
  --output <reconciliation-json>

E:\智能运营分析项目\.venv\Scripts\python.exe -B <timestamp-coverage-script> `
  --secure-config E:\智能运营分析项目_本地配置\beta10d_day4_runtime.env `
  --snapshot E:\智能运营分析项目\output\master_table.xlsx `
  --output <timestamp-coverage-json>

E:\智能运营分析项目\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider `
  --basetemp .codex_tmp\day6c_pytest_tmp tests/test_day6a_credential_redaction.py

E:\智能运营分析项目\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider `
  --basetemp .codex_tmp\day6c_pytest_day4 tests/test_day4_data_access_security.py
```

全部 SQL 为固定只读模板或只读事务中的零行拒绝探针；没有任意 SQL 接口调用。

## 7. Passed、failed、skipped

- 脱敏预检查点：11/11 hash PASS。
- 受限身份、角色属性、白名单、拒绝访问与双源表指纹子门禁：PASS；32 个查询指纹。
- 快照/PostgreSQL 对账：NOT PASS；6 个共同数值列全部精确匹配，但 2 个必需源列无数据库来源。
- 时间覆盖：NOT PASS；三张表均包含冻结快照未纳入的小时。
- 七种脱敏输出面：7/7 PASS。
- Day 6A 脱敏 pytest：首次 17 passed、1 setup error（中文绝对临时路径编码）；改用 E 盘 ASCII 相对临时路径后 18 passed、0 failed、0 skipped。
- Day 4 静态安全回归：10 passed、2 failed、0 skipped；两项因测试客户端未注入数据库配置返回 503，未触发数据库写入。任意 SQL 路由终止、动态对象路由移除、白名单静态契约和无 `GRANT ALL` 等 10 项通过。
- 阶段二至阶段五测试：0，因阶段一停止。

## 8. PostgreSQL 受限身份验证

凭据入口：项目盘外、未提交的既有本地配置；只输出路径、键名和身份分类，不输出值。

运行身份：

- `current_user=session_user=beta10d_app_login`
- `NOSUPERUSER`、`NOCREATEDB`、`NOCREATEROLE`、`NOREPLICATION`、`NOBYPASSRLS`、`LOGIN`
- database CREATE：false；public schema CREATE：false
- 事务只读：true
- Day 4 11 个注册数据集：11/11 存在且可 SELECT
- `users`、`audit_logs`、`alembic_version`、`pg_authid`、服务端文件读取：全部拒绝

安全仓储身份：

- `current_user=session_user=beta10d_security_login`
- 同样不具备超级用户、建库、建角色、复制或绕过 RLS 能力
- 允许读取 `users`、`audit_logs`
- 拒绝读取 `raw_market`、`raw_load`、`raw_weather`、`model_registry`
- 事务只读：true

停止项：`beta10d_app_login` 固有 ACL 对 `raw_market`、`raw_load`、`raw_weather` 具有 INSERT/UPDATE/DELETE，对多张正式业务表具有 INSERT/UPDATE。虽然本轮只读会话的 UPDATE WHERE false 被只读事务拒绝且实际写入为 0，但不满足本任务“受限身份不可写正式业务表”的更严格门禁。未扩大、未修复 ACL。

安全警告：外部本地配置继承了 `Authenticated Users: Modify` 和 `Users: ReadAndExecute`；本轮未修改该文件或 ACL。该问题不造成日志/Git 泄露，但不符合更严格的最小本地文件访问原则。

## 9. PostgreSQL 谱系复现结果

数据库受限指纹可复现：

| table | rows | min datetime | max datetime | content SHA-256 |
|---|---:|---|---|---|
| raw_market | 35,036 | 2024-06-19 00:00 | 2026-06-18 23:00 | `62aa263da36ef9da4c192bd0cb2576d2d861d3a9b22d045c02f69ee23ebfb2b2` |
| raw_load | 35,006 | 2024-06-19 00:00 | 2026-06-18 23:00 | `20422c0e079b697e4740b75f7318faae0b40085259d02271ba1d74c6d3f663e4` |
| raw_weather | 17,520 | 2024-06-19 00:00 | 2026-06-18 23:00 | `57d43bdf59e9e63f6be804c194df7410617db06913a64fd9d4b8e86b77bd486a` |

阶段一首末核心摘要 SHA-256 均为 `76e07b6da66328b931c91d27038e3df8a20135cd0c113bf7ed1caf1f9da9d37b`，身份、ACL、schema、Active 和三张源表完全一致；数据库非预期变化为 0。

冻结快照：

- 文件：`E:\智能运营分析项目\output\master_table.xlsx`
- SHA-256：`3055498473d86a45121408168989966da0809f4cbd4707259c7e564df489424f`
- 17,488 行，2024-06-19 00:00 至 2026-06-17 23:00。
- `da_price`、`rt_price`、`actual_load`、`forecast_load`、`temperature`、`wind_speed`：各 17,488/17,488 精确匹配，最大绝对差 0。
- PostgreSQL 当前表没有 Candidate 训练必需的 `precipitation` 和 `is_holiday` 列级来源；直接阻断 6 个降水特征和 1 个节假日特征。
- 同一时间窗内，raw_market/raw_load 各有 6 个数据库额外小时，raw_weather 有 8 个额外小时；快照时间集合与当前 PostgreSQL 不同。

因此：数据库自身指纹可复现，但冻结 Candidate 训练源与当前 PostgreSQL 的完整等价性不可证明，阶段一最终为 `NOT PASS`。

## 10. 33 项新鲜度阻塞处理结果

未执行。阶段一 NOT PASS 后立即停止；Day 6C 新处理数为 0。沿用 Day 6B 的“数据新鲜度 33 项”仅作为冻结基线，不将其改写为本轮已恢复。

## 11. 56 项 Provider 缺失处理结果及真实来源证据

未执行。阶段二未获准，因此未调用外网、未接入负荷或天气 Provider、未产生 Provider 响应、缓存、重试、时区或 24 小时窗口证据。Fake Provider 也未作为准入证据。

## 12. 模型性能下降根因与特征消融

未执行。阶段三未获准；没有把阶段一的降水/节假日谱系缺口扩写为未经验证的性能根因，也未开始调参或消融。

## 13. 新候选、训练与评估

- 新候选特征数量：0
- 新 model_version：无
- 新 feature_version：无
- 新训练/验证/测试范围：无
- 时间序列交叉验证：未执行
- 滚动回测：未执行
- 新旧模型同口径指标：未执行
- 新泄漏审计：未执行
- 新 Artifact SHA-256：无

Day 6B Candidate 和 Active 均保持冻结，未反序列化、未注册、未激活、未覆盖。

## 14. 数据库预期和非预期变化

- 预期：DDL 0、DML/业务写入 0、迁移 0、Seed 0、模型注册 0、Active 切换 0。
- 实际：与预期一致。
- 所有连接均为两个受限角色；没有使用 `postgres`。
- 只读事务写探针均被拒绝；三张源表和核心身份/ACL/schema/Active 的首末摘要哈希一致。
- 新数据库、新 Schema、临时角色、正式业务表写入：0。

## 15. 敏感信息扫描

- 统一脱敏函数覆盖 stdout、stderr、日志、JSON、Markdown、TXT 和异常链：7/7 PASS。
- 现有脱敏 pytest 最终：18 passed。
- 完整凭据、完整 DSN、环境变量正文、Token、API Key、Secret、Authorization Header：未写入证据、报告、diff 或提交。
- 提交前扫描：30 个文件、4 个已知敏感值；文件命中 0、diff 命中 0、哨兵原文命中 0、已知凭据值命中 0、敏感模式命中 0，`PASS`。本地证据：`sensitive_scan.json`。

## 16. RAG 隔离

三条 RAG 工作树 HEAD 与 clean 状态保持不变；merge、cherry-pick、文件复制、Router/权限/迁移/公共配置修改和 RAG 数据库写入均为 0。

## 17. 回滚

- 代码/文档：对 Day 6C 收口提交执行 `git revert <commit>`；不使用 reset 或 clean。
- 数据库：无数据库变化，无数据回滚动作。
- Active/Candidate：从未修改，无模型回滚动作。
- 外部凭据文件：未改内容、未改 ACL，无配置回滚动作。
- 本地忽略证据保留；如需物理删除，必须按仓库规则逐个明确路径另行确认，本轮不删除。

## 18. 未解决项

1. 将 Day 6C 数据核验身份收紧为不可写正式业务表的专用只读角色，或经批准精确收紧现有 ACL；不得扩大权限。
2. 修复项目盘外凭据文件的本地 ACL，并提供可回滚的权限变更证据。
3. 为 Candidate 必需的 `precipitation` 与 `is_holiday` 建立符合 Day 4 白名单和预测时点语义的正式来源；不得读取未登记 `raw_json` 旁路。
4. 解释并可复现冻结快照排除 6/8 个数据库小时的规则，生成严格时间集合清单与转换版本。
5. 上述阶段一阻塞全部关闭后，才允许重新启动 Day 6C 阶段一；不得跳到阶段二。

## 19. 最终准入

- PASS / CONDITIONAL PASS / NOT PASS：`NOT PASS`
- 是否允许重新进入 Day 6A：`NO`
- 是否允许进入原 Day 6：`NO`
- 是否允许进入 Day 7：`NO`
