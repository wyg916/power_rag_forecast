# 最终路径门禁与回滚

## 当前冲突

用户最初指定的最终路径：

`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`

该路径当前不是 Release，而是：

- 分支：`codex/p6-home-dashboard-readability-20260813`
- SHA：`e98010f664921b033eb91cb53d9b8dcd236e7f19`
- 状态：clean

真正 Release 分支当前位于：

`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807_report_integration`

因此，在没有明确授权时把原路径切回 Release 会批量覆盖该路径中的首页候选文件，触发 AGENTS.md 停止条件。本次没有执行该动作，也没有更新 Release 分支指针。

## 获授权后的最小动作

1. 再次保存两个工作树的 status、HEAD、diff、未跟踪文件和关键哈希。
2. 保留首页候选分支 `codex/p6-home-dashboard-readability-20260813` 与 SHA `e98010f…`，不删除任何文件或分支。
3. 将当前 Release worktree 临时停放到明确的保留分支，使 `release/beta10d-agent-rc-20260807` 可被最终路径检出。
4. 将 Release 仅快进到本隔离集成最终提交；不 rebase、不推送。
5. 在用户最初指定的最终路径检出 Release，运行 `run_project.bat`，重新核对三页视觉、全部适用控件、Console、Network、API/数据库、build、双启动与 Git clean。

## 回滚

- Release 回滚点：`b4cfdd06dc9fb63ebbc66565531f9a5c40f4b589`。
- 首页候选回滚点：`e98010f664921b033eb91cb53d9b8dcd236e7f19`。
- 隔离集成失败时只需放弃 `codex/integrate-forecast-center-20260815`；当前 Release 和首页候选均未被修改。
