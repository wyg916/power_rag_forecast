# 回滚

- 首选：对本任务最终提交执行 `git revert <commit>`。
- 文件级恢复：使用 `backups/phase3/20260828_151052_RUN_PROJECT_STARTUP_FIX_PRE/originals/` 中的原件。
- 当前差异已通过 `git diff --binary | git apply --reverse --check`，反向补丁可用。
- 禁止使用 `git reset --hard`；不删除用户文件。
- 本任务没有数据库迁移或业务数据写入，无数据库回滚步骤。
