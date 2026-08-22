# 项目一 v2.12.0 并行执行清单

## 1. 冻结身份

- 任务：`PROJECT1_V2_12_MASTER_BOOTSTRAP_AND_PARALLEL_ORCHESTRATION`
- 基线 worktree：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`
- 基线分支：`release/beta10d-agent-rc-20260807`
- 基线 SHA：`736a39719613a9b14b5f9c94b83e727271764f98`
- 基线 Tag：`project1-v2.11.2-local-final-rc-20260816`
- 目标版本：`v2.12.0`
- 目标阶段：`LOCAL_FINAL_RC`
- 本清单所在提交为并行任务的 `INTEGRATION_SEED_SHA`；精确 40 位值由 Bootstrap 最终输出记录，并以各任务 worktree 的 `git rev-parse HEAD` 复核。

## 2. 唯一工作线

| 角色 | 分支 | worktree | 合并权限 |
|---|---|---|---|
| Final Integration | `codex/project1-v2.12.0-final-integration` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_final_integration` | 唯一合并负责人 |
| A 核心 P0 | `codex/project1-v2.12.0-core-p0` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_core_p0` | 禁止合并/cherry-pick |
| B UI/RBAC/AI Shell | `codex/project1-v2.12.0-ui-rbac-ai-shell` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_ui_rbac_ai_shell` | 禁止合并/cherry-pick |
| C AI Runtime/Release | `codex/project1-v2.12.0-ai-runtime-release` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_ai_runtime_release` | 禁止合并/cherry-pick |

Bootstrap、A、B、C 均不得更新 `main`、创建正式 Tag、删除历史资产或处理其他任务分支。Final Integration 仅在 A/B/C 都为 `READY_FOR_INTEGRATION=YES`、工作树 clean 且文件所有权审计通过后执行合并。

## 3. 启动门禁

每个任务开始前必须输出并核对：

```powershell
Get-Location
git branch --show-current
git rev-parse HEAD
git status --short --branch
```

要求：路径与本表一致，HEAD 等于 Bootstrap 最终输出中的 `INTEGRATION_SEED_SHA`，工作树 clean。任一不符立即停止，不得 reset、clean、stash、切换到其他分支或猜测基线。

## 4. 执行顺序

1. A/B/C 从同一 `INTEGRATION_SEED_SHA` 并行开发，各自只修改所有权范围。
2. 各任务以小提交交付状态文件、证据和准确的 PASS/PARTIAL/FAIL，不得自行合并。
3. Final Integration 按 A → C → B 顺序使用可追溯 merge commit 合入。
4. 任一冲突先依据 `INTERFACE_CONTRACT.md` 与 `FILE_OWNERSHIP.md` 判定；无法唯一判定则停止。
5. 全量验收只认最终集成分支同一个候选 `FINAL_SHA`，不得拼接不同 SHA 的历史 PASS。

## 5. 全局禁止项

- 不修改、reset、clean、覆盖普通根目录 `E:\智能运营分析项目` 的用户改动。
- 不删除历史分支/worktree、数据库、Docker volume、模型、RAG/Qdrant 索引或证据。
- 不停止来源不明的端口进程；端口冲突只报告来源或采用可回滚方案。
- 不打印/提交密钥、Token、密码、私钥正文或完整 DSN。
- 不使用 Mock、Demo、固定值、历史结果或 fallback 伪造成功。
- 不激活生产模型，不切换 RAG production alias，不执行生产流量切换。
- GET/查询不得隐式 seed、同步、激活或产生其他写副作用。
- 无权限、无证据、解析失败、Provider 失败必须显式失败，禁止假成功。

## 6. 权威输入

- `docs/codex/final_local_closeout/PROJECT1_FINAL_BASELINE.md`
- `docs/codex/final_local_closeout/FULL_REGRESSION_REPORT.md`
- `docs/codex/final_local_closeout/PREDICTION_TASK_STATUS_CLOSURE_REPORT.md`
- `docs/codex/final_functional/PAGE_ACCEPTANCE_MATRIX.md`
- `docs/codex/security/API_PERMISSION_MATRIX.csv`
- 外部审计报告与 v2.12.0 两天收口方案（实际文件名带副本后缀，Bootstrap 已只读核对）

现有基线事实只能作为回归下限和风险输入，不能作为 v2.12.0 新鲜验收结果。
