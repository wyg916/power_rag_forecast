# 回滚

- 首选：对本任务集成提交执行 `git revert <integration_commit>`，生成可审计反向提交。
- 文件级：检查点 `E:\智能运营分析项目\backups\phase3\20260827_013459_PROJECT1_PREDICTION_CENTER_INTEGRATION_PRE` 保存了候选代码原件、状态、diff、控件基线和 SHA-256；覆盖恢复前需人工确认。
- 核验：恢复后复算 `critical_hashes.csv`，运行 TypeScript、前端单测、预测静态测试和生产构建。
- 数据库/API/模型/配置影响：NONE，不需要数据迁移或数据恢复。
- 禁止使用 `git reset --hard` 或清理其他未提交文件。
