# PROJECT1 v2.12.0 最终发布基线

## 发布身份

- 目标版本：`v2.12.0`
- 目标阶段：`LOCAL_FINAL_RC`
- 权威 Integration 分支：`codex/project1-v2.12.0-final-integration`
- 原始权威基线：`736a39719613a9b14b5f9c94b83e727271764f98`
- A 最终提交：`3aa38348d5822f69c21dd8aee93a6ac0ade00001`
- C 最终提交：`521f18a9ad651dc1edcf0358a27cc78a35bf6944`
- B 最终提交：`4d1d87463dd4e45f8f01cb15ce958711f6e06099`
- Stage 2 候选：`f56d4a73cf8d2de4dfe2eea5e1aebf5ce3561575`
- Round 1 代码候选：`44e048d56ccc8f21ac60bc52881b2b806f97d92f`
- 附件/Provider/RBAC 阻断修复提交：`a073f96b67d3d2b387ef51dee905e055dc983c69`
- 前一失败预发布 SHA：`dfd9ebe958762aa30792b8681521f5dd67aa4e22`
- 权限矩阵漂移修复提交：`c1e33b3e500874497276a8d0ffff1119d5fcee2a`
- `FINAL_PRE_RELEASE_SHA`：`SELF`，即包含本文件在内的单次发布文件提交；随后所有 tracked 文件冻结并执行 SAME-SHA Round 2。
- `FINAL_SHA`：仅当 Round 2 全部硬门禁通过后，等于 `FINAL_PRE_RELEASE_SHA`。

## 冻结规则

1. A/B/C 分支保持冻结，后续发布阻断只允许在唯一 Integration 分支修复。
2. Round 2 开始后，所有测试必须针对同一个 `FINAL_PRE_RELEASE_SHA`；日志仅写仓库外证据目录。
3. Round 2 通过后禁止再修改 tracked 文件、amend、rebase 或制造额外发布提交。
4. 不允许 Mock、Demo、历史结果复制、固定值或 fallback 伪造成功。
5. 本地 RC 不等于生产发布。模型 Active、RAG production alias 和 Production Go-Live 均不在本任务授权范围。

## Round 1 冻结结果

Round 1 在 `44e048d56ccc8f21ac60bc52881b2b806f97d92f` 的最终代码状态完成。该提交相对上一候选只修改运行控制脚本与对应测试；在其父提交完成且不受该差异影响的浏览器、预测、ChatBI、Provider、附件和 Memory 证据，通过 ancestry 与文件差异核验纳入 Round 1。

- Git/fsck：PASS
- Migration：PASS；单 head/current=`0022_chatbi_semantic_v1`，upgrade/downgrade/re-upgrade 与 residue=0
- Backend：1190 collected / 1156 passed / 34 skipped / 0 failed / 0 errors
- Frontend：lint、unit、typecheck、Vite build 全部 PASS
- UI：32 路由 × 4 viewport = 128/128 PASS
- Prediction：SUCCESS，24 行，0 partial，0 fake success，下游链 PASS
- ChatBI：Golden 50/50，LLM 任意 SQL 执行次数 0
- 三模型路由：MiMo、DeepSeek、Kimi 最小真实调用 PASS；静默 Premium 0
- 浮动 AI、附件生命周期、RBAC、Memory：PASS
- RAG：50 问质量、安全与只读门禁 PASS；未切 production alias
- Startup：cold start、第二次幂等 start、restart、controlled stop PASS
- Security：高置信密钥发现 0，越权数据访问 0

## 阻断修复冻结结果

- Settings Read / Strategy Review RBAC：PASS；已知未授权请求 0
- DeepSeek `DATA_PLANNER` 真实 AnalysisPlan：PASS；schema/semantic PASS；raw SQL 0
- Attachment evaluator A–F：PASS；Grounding/Citation 独立判定
- 真实附件 selected-only QA：调用 1、retry 0、附件 chunk 1、Enterprise KB chunk 0、Citation 1、Grounding/Citation PASS
- `ATTACHMENT_PROVIDER_RBAC_REMEDIATION_SHA=a073f96b67d3d2b387ef51dee905e055dc983c69`

## 权限矩阵漂移修复冻结结果

- 前一预发布 `dfd9ebe958762aa30792b8681521f5dd67aa4e22` 的 SAME-SHA Backend Full 唯一失败为矩阵复现漂移：1172 passed、34 skipped、1 failed、0 errors；该 SHA 已废止为最终候选。
- 既有生成器从 runtime route dependency、权限映射与角色注册表同步生成 CSV/Markdown；四个 Settings GET 现为 `settings:read`，三个相关写路由仍为 `settings:write`。
- generator reproducibility、Python 54、frontend permission policy 4 与提交前 Backend Full 1173 passed/34 skipped/0 failed/0 errors 均 PASS；public match，临时 schema/role 残留 0。
- `PERMISSION_MATRIX_REMEDIATION_SHA=c1e33b3e500874497276a8d0ffff1119d5fcee2a`

以上是进入新候选单次 SAME-SHA Full Regression 的前置结果，不代替最终同 SHA 回归。

## 生产外部门禁

- `PRODUCTION_GO_LIVE=NOT_EXECUTED`
- TLS production acceptance：`NOT_EXECUTED`
- Secret Manager production integration：`NOT_EXECUTED`
- production alerting/SLO：`NOT_EXECUTED`
- capacity/long-run：`NOT_EXECUTED`
- disaster recovery：`NOT_EXECUTED`
- external approval：`NOT_EXECUTED`

本文件没有任何生产通过或生产就绪声明。
