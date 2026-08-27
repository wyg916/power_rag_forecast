# 回滚说明

- 当前工作只存在于独立分支 `codex/strategy-center-ui-review-v2`，尚未合入 `main`。
- 修改前检查点：`backups/phase3/20260828_000000_PROJECT1_STRATEGY_FINAL_UI_PRE`。
- 若人工审核不通过，可在独立分支上按文件恢复检查点副本，或丢弃本轮最终提交；不需要数据库回滚。
- 不执行 `git reset --hard`、`git clean` 或批量删除。
