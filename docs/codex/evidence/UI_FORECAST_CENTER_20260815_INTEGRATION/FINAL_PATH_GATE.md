# 最终路径门禁、重定位与回滚

## 已执行结果

- 用户指定最终路径：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`。
- 最终分支：`release/beta10d-agent-rc-20260807`。
- 集成内容提交：`a3135a67ac3555af5c1979168d8bb210cab7d34b`。
- 数据中心提交 `a6c3bfdca8a181c7f5051b8d0933579eb5d58f2f` 与用户批准预测候选 `7090de4f76a4df228f7b98e9203b205c5aeba0fd` 均为该提交祖先。
- REJECTED 候选 `bc8c4c568fe838cc6927890d0d6c20bb760fa730` 和首页候选 `e98010f…` 均不是该提交祖先。
- 首页候选继续保留在 `codex/p6-home-dashboard-readability-20260813` / `e98010f664921b033eb91cb53d9b8dcd236e7f19`。
- 原 Release worktree 停放于 `codex/hold-release-before-forecast-20260815` / `a6c3bfdca8a181c7f5051b8d0933579eb5d58f2f`。

检查点：`E:\智能运营分析项目_worktrees\_checkpoints\forecast_center_final_relocation_post_data_20260815`。

## 回滚

1. 停止最终路径启动的 5190/8030 服务。
2. 将 `release/beta10d-agent-rc-20260807` 快进前指针恢复到 `a6c3bfdca8a181c7f5051b8d0933579eb5d58f2f`；该动作会改写分支指针，执行前须再次获得用户确认。
3. 首页候选无需恢复，仍由 `codex/p6-home-dashboard-readability-20260813` / `e98010f…` 独立保留。
4. 需要审计时使用上述检查点复核 Git 状态、关键哈希和数据库零迁移说明。
