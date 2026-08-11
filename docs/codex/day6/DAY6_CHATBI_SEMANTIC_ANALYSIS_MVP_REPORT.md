# Day6 ChatBI Semantic Analysis MVP 闭环报告

## 1. 结论

`DAY6 CHATBI SEMANTIC ANALYSIS MVP / PACKAGE 1–5 = PASS（本地开发/预发布等效）`。

五个任务包在同一分支 `codex/day6-chatbi-semantic-analysis-mvp` 上从 Day5 Unified RC `0380f4cbc8e2685dd89572dfa0b678cf7b533a05` 严格串行演进，每包均有独立 PRE、专项测试、相关回归、数据库影响记录、证据目录和独立提交。Package 5 通过后只允许继续执行 DAY6 RC-CONVERGENCE CHECKPOINT；本报告不表示生产发布许可。

## 2. 连续提交链与检查点

- Package 1：`976236ba04ba1b4b01a1ffbb2d0e081de25be157`
- Package 2：`9a08ce38e886f2eb3a44dbb5d627a690e1796565`
- Package 3：`63b653beeaf51203cdaab2dcb701d3988530b724`
- Package 4：`72e4df044c90d69a6866d01c3209dfff6ec7f175`
- Package 5：本报告所在提交
- Package 5 starting SHA：`72e4df044c90d69a6866d01c3209dfff6ec7f175`
- Package 5 PRE：`backups/phase3/20260811_163741020_DAY6_CHATBI_PKG5_PRE`
- Package 5 证据：`docs/codex/evidence/DAY6_CHATBI_PKG5_20260811_163741020`

Package 5 commit 统计：10 files changed / 501 insertions / 4 deletions；测试统计见第 4、5 节。

## 3. 交付能力

- 冻结 Golden 50 题集与 SHA-256，完整覆盖单/多指标、Group By、Time Series、YoY、MoM、Ranking、Contribution、Drill Down、白名单 Join、歧义澄清、空数据、数据不足、越权、Prompt Injection、ChartSpec 与 Multi-turn；未删除难题或降低门槛。
- Golden 执行器使用冻结 Plan LLM seam，但真实经过 `AnalysisPlan → Validator → Compiler → PostgreSQL → Result Dataset → ChartSpec → Narrative`，并逐题校验安全、执行、聚合、比较、Join、图表、叙述、澄清和多轮语义。
- 修正全 NULL 聚合行被误判成功的问题；无比较值时返回 Empty，比较当前/历史均缺失时继续返回 Insufficient。
- Golden 隔离夹具仅在受限临时 Schema 内按真实字段补齐实时价与边际价，数据进入 PostgreSQL 后再被编译查询；没有前端 Mock、hardcode 或成功态 fallback。
- Assistant 经营分析页面保持 Table/ChartSpec 共享同一 AnalysisPlan、Result Dataset 与 result_hash；1280px 输入区工具按钮可换行，发送按钮不再被裁切。
- Day2 迁移静态门禁已登记唯一 `0022`；不存在会话反馈保持 404，数据库不可用保持 503，均不制造成功响应。

## 4. Package 5 验证

| 门禁 | 结果 |
|---|---|
| ChatBI Golden 50 | PASS，50/50；全部评分维度 100% |
| Day2/Day4/Day5 Memory + ChatBI Memory | PASS，33 passed |
| RAG 回归 | PASS，69 passed |
| RBAC / Security | PASS，165 passed |
| Backend release matrix | PASS，214 passed；2 个 Celery 重名 warning，不影响状态 |
| Package 5 改动点复验 | PASS，7 passed |
| Frontend TypeScript + Vite | PASS，3,675 modules |
| Browser E2E | PASS；隔离登录、Assistant、经营分析、业务空态、1280px 无页面溢出、console warning/error 0 |
| `run_project.bat` | PASS，连续两次；第二次复用健康服务 |
| Alembic | PASS，唯一 head `0022_chatbi_semantic_v1` |

所有 PostgreSQL 集成矩阵均使用受限临时 Schema；每次 public 前后指纹一致，临时 Schema/角色残留为 0。Golden 的 `raw_market` 受控夹具补值及 Memory/API/Browser 写入均随临时 Schema 清理。

## 5. 全仓 diagnostic

全仓结果为 `965 passed / 39 skipped / 44 failed / 32 errors`，没有宣称全仓全绿。完整分类见 `full_diagnostic_classification.md`：

- RELEASE_BLOCKING fail/error：0
- LEGACY_OUT_OF_SCOPE fail/error：2
- EXTERNAL_ENVIRONMENT fail/error：74
- EXTERNAL_ENVIRONMENT skip：39
- UNCLASSIFIED_FAIL：0
- UNCLASSIFIED_ERROR：0

相较 Day5 基线 `916 passed / 34 skipped / 46 failed / 32 errors`，fail 减少 2、error 不增加；当前 ChatBI、Memory、RAG、Security 和 Backend 发布矩阵均独立全绿。

## 6. 数据库、模型与发布边界

- Package 1 创建唯一迁移 `0022_chatbi_semantic_v1`，已执行公共库和隔离库 upgrade → downgrade → re-upgrade；Package 2–5 迁移新增为 0。
- Package 5 公共业务写入 0；隔离测试写入均已清理。GET/查询路径未产生 seed、激活或同步副作用。
- LLM SQL 直接执行、任意 SQL、前端拼 SQL、未注册指标/字段执行均为 0。
- 模型 Candidate/Active 状态修改 0，RAG production alias 修改 0，Qdrant 持久写操作 0，远端推送 0，生产发布 0。

## 7. 回滚

1. Package 5 代码回滚使用对本报告所在提交的普通 `git revert`，不得强制 reset。
2. Package 5 无公共数据库结构或业务写入，因此不需要数据恢复；隔离测试对象已经清零。
3. 如需回滚整个 Day6，须按 Package 5 → 1 逆序 revert；仅在确认 0022 表无后续业务事实后，才可依据 Package 1 已验证路径 downgrade 到 `0021_memory_lifecycle_v1`。
4. 完整任务前恢复依据为五个项目盘 PRE 检查点，不涉及 C 盘或生产环境。

## 8. 后续门禁

不得直接进入 Day7。下一步仅执行 DAY6 RC-CONVERGENCE CHECKPOINT：将完整链 ff-only 收回 `release/beta10d-agent-rc-20260807`；若出现 divergence 必须停止。收敛后重新执行用户指定的最小统一门禁，全部通过后方可登记 UNIFIED RC PASS。
