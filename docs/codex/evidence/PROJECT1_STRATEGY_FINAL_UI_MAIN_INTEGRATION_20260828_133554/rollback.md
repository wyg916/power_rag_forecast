# 回滚方案

1. 首选以检查点恢复合入前状态：`E:/智能运营分析项目/backups/phase3/20260828_133554_PROJECT1_STRATEGY_FINAL_UI_INTEGRATION_PRE`。
2. Git 可按逆序创建回滚提交：先回滚本次证据提交，再依次回滚 `9d097b6`、`cb83ec9`、`0848db8`。
3. 不使用 `git reset --hard`、不删除用户文件。
4. 数据库无需回滚，因为本次数据库、迁移和业务状态写入均为 0。
