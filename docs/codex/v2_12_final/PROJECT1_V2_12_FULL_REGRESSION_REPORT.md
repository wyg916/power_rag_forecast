# PROJECT1 v2.12.0 Full Regression Report

## 范围与判定

- Round 1 最终代码 SHA：`44e048d56ccc8f21ac60bc52881b2b806f97d92f`
- 证据根目录：`E:\项目一_v2.12.0_备份\FINAL_REGRESSION_20260823_005414508`
- Round 1：`PASS`
- Round 2 SAME-SHA：在发布文件提交形成 `FINAL_PRE_RELEASE_SHA` 后执行；本报告提交时为 `PENDING`。
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

## 环境失误与有效结果选择

以下尝试被保留为审计证据，但不作为产品失败计数：

- 后端 v1：PowerShell JUnit 参数错误，未执行测试。
- 后端 v2：错误注入 enterprise RAG 环境且缺少模型资产根，产生环境性失败。
- Security v1：未启用隔离数据库环境。
- RAG Formal 50 初次并发配置 P95=2132.6ms，质量和安全通过但性能门禁失败；随后使用固定、可复现的本机 RC 验收并发配置重新执行并通过。

权威后端结果为 v3：直接使用 Day3 隔离 guard，并设置本地模型资产根；公共 schema 未改变，临时 schema/role 清理完成。

## 未执行的生产门禁

`PRODUCTION_GO_LIVE=NOT_EXECUTED`。生产 TLS、Secret Manager、告警/SLO、容量/长稳、DR、外部审批均 `NOT_EXECUTED`，本报告不声称生产就绪。
