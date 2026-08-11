# Day6 RC-Convergence Checkpoint 报告

## 1. 最终结论

- `DAY6 CHATBI SEMANTIC ANALYSIS MVP = PASS`
- `UNIFIED RC = PASS`
- `RELEASE_BLOCKING = 0`
- `UNCLASSIFIED_FAIL = 0`
- `UNCLASSIFIED_ERROR = 0`

Day6 五个任务包已从 Day5 Unified RC 严格串行演进，并通过 `ff-only` 收回 `release/beta10d-agent-rc-20260807`。收敛后的代码门禁验证 SHA 为 `1e76b74ad4e23b020561b653df4aead3dd6a898b`；本报告所在提交只登记门禁结果，不改变运行代码。

本结论仅代表本地开发/预发布等效 RC 门禁通过，不代表生产发布许可；未进入 Day7。

## 2. 连续提交链

1. Day5 Unified RC：`0380f4cbc8e2685dd89572dfa0b678cf7b533a05`
2. Package 1：`976236ba04ba1b4b01a1ffbb2d0e081de25be157`
3. Package 2：`9a08ce38e886f2eb3a44dbb5d627a690e1796565`
4. Package 3：`63b653beeaf51203cdaab2dcb701d3988530b724`
5. Package 4：`72e4df044c90d69a6866d01c3209dfff6ec7f175`
6. Package 5：`17e2f8bf55332ae43d5af6c27474f176da71f7b4`
7. RC 换行符兼容修复：`1e76b74ad4e23b020561b653df4aead3dd6a898b`

Package 1–5 均在 `codex/day6-chatbi-semantic-analysis-mvp` 上独立提交；未创建包级长期功能分支。收敛前 RC 与功能分支没有双向提交，所有收回均为 `ff-only`，没有 merge commit 或复杂合并。

RC 收敛 PRE：`backups/phase3/20260811_182808153_DAY6_RC_CONVERGENCE_PRE`。

## 3. 收敛过程与已关闭异常

首次快进后，Golden 50 在 Windows 第二工作树因 Git checkout 将 JSONL 的 LF 转为 CRLF，原始字节 SHA-256 产生假阳性资产篡改告警。门禁按约束停止，未继续后续验证。修复只对校验输入做换行符规范化，没有修改题集、预期答案、难题或安全阈值；新增 LF/CRLF 等价回归，6 项 Package 5 单测通过，然后以独立提交再次 `ff-only` 收敛。

修复后第一次隔离执行遗漏显式设置 Day6 预期迁移 head，守卫按旧默认值在执行 Golden 前停止；public 指纹一致，临时 Schema/角色均清理。补充 `BETA10D_TEST_EXPECTED_ALEMBIC_HEAD=0022_chatbi_semantic_v1` 后重跑通过。另有一次外层日志采集命令在 60 秒超时，未计入启动 PASS；随后保留两次完整、连续、退出码 0 的 `run_project.bat` 证据。

上述异常均已分类、关闭并留下证据，不存在未分类失败或错误。

## 4. 更新后唯一 RC 门禁

| 门禁 | 结果 |
|---|---|
| Alembic unique head | PASS，唯一 `0022_chatbi_semantic_v1` |
| ChatBI Golden 50 | PASS，50/50；全部适用评分维度 100% |
| Day2/Day4/Day5 + ChatBI Memory | PASS，33 passed / 0 failed / 0 errors / 0 skipped |
| RAG smoke | PASS，69 passed / 0 failed / 0 errors / 0 skipped |
| RBAC / Security | PASS，166 passed / 0 failed / 0 errors / 0 skipped |
| Frontend TypeScript + Vite | PASS，3,675 modules |
| Browser smoke | PASS；隔离登录、Assistant、经营分析、可信空态；1280×800 横向溢出 0，发送按钮完整可见，页面 console warning/error 0 |
| `run_project.bat` | PASS，连续两次退出码 0；第二次复用健康服务 |
| Git | PASS；报告提交前 RC 与功能分支差异 `0 0`，工作树 clean |

Package 5 已完成的全仓 diagnostic 保持为 `965 passed / 39 skipped / 44 failed / 32 errors`，完整分类为 RELEASE_BLOCKING 0、LEGACY_OUT_OF_SCOPE 2、EXTERNAL_ENVIRONMENT fail/error 74、EXTERNAL_ENVIRONMENT skip 39、UNCLASSIFIED_FAIL 0、UNCLASSIFIED_ERROR 0。收敛后按约束只重跑最小统一门禁，没有重复执行全仓 900+ 测试。

## 5. 数据库与安全边界

- 所有 PostgreSQL 集成门禁均在受限临时 Schema/角色内运行，public 前后指纹一致，临时 Schema/角色残留均为 0。
- 收敛阶段 public 业务写入 0；Golden 受控夹具和 Memory/API/Browser 测试写入随临时 Schema 清理。
- 唯一新增迁移仍为 Package 1 的 `0022_chatbi_semantic_v1`；Package 2–5 与收敛修复新增迁移 0。
- `LLM → AnalysisPlan → Validator → Query Compiler → PostgreSQL` 正式路径保持；LLM SQL 直执行、任意 SQL、前端拼 SQL、未注册指标/字段直接查询均为 0。
- cross-user / cross-tenant 泄漏 0，SQL 安全边界破坏 0，Memory/RAG 已通过能力退化 0。

## 6. 发布边界与回滚

- 远端推送 0，生产部署 0，模型 Candidate/Active 变更 0，RAG production alias 切换 0。
- 代码回滚使用对收敛提交链的普通 `git revert`，不得强制 reset。
- 如需回滚唯一迁移，必须先确认 `0022` 表无后续业务事实，再按 Package 1 已验证路径 downgrade 到 `0021_memory_lifecycle_v1`。
- RC 收敛检查点可用于恢复收敛前 Git 状态；本轮没有需要数据恢复的公共业务写入。

## 7. 证据

- Package 5 总报告：`docs/codex/day6/DAY6_CHATBI_SEMANTIC_ANALYSIS_MVP_REPORT.md`
- Package 5 证据：`docs/codex/evidence/DAY6_CHATBI_PKG5_20260811_163741020`
- RC convergence 证据：`docs/codex/evidence/DAY6_RC_CONVERGENCE_20260811_182808153`

证据目录包含 Golden 结果与隔离守卫、Memory/RAG/Security JUnit 与隔离守卫、Browser smoke、两次启动日志及统一摘要。
