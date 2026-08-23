# PROJECT1 v2.12.0 Full Regression Report

## 范围与判定

- 历史 Round 1 最终代码 SHA：`44e048d56ccc8f21ac60bc52881b2b806f97d92f`
- 附件/Provider/RBAC 阻断修复提交：`a073f96b67d3d2b387ef51dee905e055dc983c69`
- 前一失败预发布 SHA：`dfd9ebe958762aa30792b8681521f5dd67aa4e22`
- 权限矩阵漂移修复提交：`c1e33b3e500874497276a8d0ffff1119d5fcee2a`
- 证据根目录：`E:\项目一_v2.12.0_备份\FINAL_REGRESSION_20260823_005414508`
- Round 1：`PASS`
- Remediation Targeted Gate：`PASS`
- 前一 Round 2 SAME-SHA：`FAIL`；Backend Full 为 1207 collected / 1172 passed / 34 skipped / 1 failed / 0 errors，唯一失败是权限矩阵生成物未同步四个 Settings GET runtime guard。因本次修复产生新代码提交，该 SHA 不再是最终候选。
- 新 Round 2 SAME-SHA：本发布文件所在提交为 `FINAL_PRE_RELEASE_SHA=SELF`；提交后冻结 tracked 文件并仅执行一次，本报告冻结时为 `PENDING`。
- 生产发布：`NOT_EXECUTED`

## Round 1 权威结果

| 门禁 | 结果 | 关键计数/说明 |
|---|---|---|
| Git | PASS | clean；`git fsck --full --strict` exit 0 |
| Migration | PASS | single head/current `0022_chatbi_semantic_v1`；rollback/re-upgrade；residue=0 |
| Backend full | PASS | 1190 collected；1156 passed；34 skipped；0 failed；0 errors |
| Frontend | PASS | lint、26/26 unit、typecheck、Vite build 3682 modules |
| Prediction gates | PASS | contract/model/dispatcher 40；transaction/failure gates 19；fail-closed 覆盖完整 |
| Prediction fresh E2E | PASS | `run_20260822T190147191292Z_04ced065c8`；24 rows；0 partial；下游同 run_id |
| ChatBI | PASS | contracts 50/50；Golden 50/50；LLM raw SQL execution=0 |
| Provider | PASS | MiMo general/vision、DeepSeek plan/complex、Kimi explicit Premium；fallback max=0 |
| UI | PASS | 32 routes；4 viewports；128/128；subtitle/raw metadata/raw403/browser errors 均 0 |
| Role RBAC | PASS | 4 roles；20/20 allowed/denied cases；unauthorized data access=0 |
| Floating AI / Attachment | PASS | 会话与页面上下文、8 个附件来源、引用、删除后不可复用、跨用户隔离 |
| RAG | PASS | 50 questions；Recall@3/5=1；MRR=.9467；P95=803.891ms；Qdrant writes=0 |
| Memory | PASS | 9/9 live gates；隔离、读写、幂等、回滚、TTL/legal hold/delete/trace |
| Runtime | PASS | cold start、second idempotent start、doctor/logs/restart/controlled stop；visible console=0 |
| Security | PASS | 156 targeted security contracts；secret findings=0；tracked large files=0 |

## Remediation Targeted Gate

| 门禁 | 结果 | 关键证据 |
|---|---|---|
| RBAC Settings | PASS | Developer 四个只读接口允许；写/测试动作继续 403 |
| Analyst Strategy Review | PASS | 无 `strategy:review` 时不进入 review 模式、不请求 review history |
| DeepSeek AnalysisPlan | PASS | `DATA_PLANNER -> deepseek-chat`；HTTP/Adapter/schema/semantic 全 PASS；raw SQL execution=0 |
| Evaluator offline A–F | PASS | Grounding 与 Citation 独立判定，六种正反组合符合冻结预期 |
| Attachment real QA | PASS | 调用 1、retry 0、output 233/上限 300；事实命中；附件 chunk 1；Enterprise KB chunk 0；Citation 1 |
| Scope/secret gate | PASS | 19 个 remediation 文件均在授权白名单；高置信 secret pattern 0 |

本节证据：`docs/codex/v2_12_final/ATTACHMENT_EVALUATOR_REMEDIATION_REPORT.md` 与 `docs/codex/v2_12_final/evidence/attachment_real_qa_20260823_141859563.json`。历史 Round 1 不能替代后续 SAME-SHA Round 2；最终结论只以 `FINAL_PRE_RELEASE_SHA` 的新执行结果为准。

## Permission Matrix Drift Closure

| 门禁 | 结果 | 关键证据 |
|---|---|---|
| Source of Truth | PASS | 既有生成器从 runtime route dependency、权限映射和角色注册表生成 CSV/Markdown；CSV 是运行时机器可读策略快照 |
| 四个 Settings GET | PASS | `/interfaces`、`/interfaces/configs`、`/interfaces/overview`、`/interfaces/test-logs` 的 runtime 与 matrix 均为 `settings:read` |
| Settings writes | PASS | `PUT /interfaces/{interface_id}`、`POST /interfaces/{interface_id}/test`、`POST /interfaces/test-all` 均继续为 `settings:write` |
| Reproducibility | PASS | 207 method+path；191 path；仅两份同步生成物各四行变化；drift=0 |
| Targeted | PASS | Python 54 passed；frontend permission policy 4 passed |
| Backend Full（提交前） | PASS | 1207 collected；1173 passed；34 skipped；0 failed；0 errors；public match；临时 schema/role 残留 0 |

证据索引：`docs/codex/evidence/PROJECT1_V2_12_PERMISSION_MATRIX_DRIFT_20260823_144740484/README.md`；仓库外原始证据：`E:\项目一_v2.12.0_备份\PERMISSION_MATRIX_DRIFT_20260823_144740484`。本节仍只是新 SAME-SHA Full Regression 的前置门禁。

## 环境失误与有效结果选择

以下尝试被保留为审计证据，但不作为产品失败计数：

- 后端 v1：PowerShell JUnit 参数错误，未执行测试。
- 后端 v2：错误注入 enterprise RAG 环境且缺少模型资产根，产生环境性失败。
- Security v1：未启用隔离数据库环境。
- RAG Formal 50 初次并发配置 P95=2132.6ms，质量和安全通过但性能门禁失败；随后使用固定、可复现的本机 RC 验收并发配置重新执行并通过。

权威后端结果为 v3：直接使用 Day3 隔离 guard，并设置本地模型资产根；公共 schema 未改变，临时 schema/role 清理完成。

## 未执行的生产门禁

`PRODUCTION_GO_LIVE=NOT_EXECUTED`。生产 TLS、Secret Manager、告警/SLO、容量/长稳、DR、外部审批均 `NOT_EXECUTED`，本报告不声称生产就绪。
