# Rollback

- 任务前检查点：`backups/phase3/20260827_015230475_T022_MODEL_CENTER_UI_REFINEMENT_PRE`。
- 提交后优先执行 `git revert <本任务提交>`。
- 未提交时可恢复检查点中的 `ModelCenterPage.tsx.original`，并删除新增的 `frontend/src/pages/model/model-center-workspace.css`。
- 本任务无数据库、迁移、模型状态和配置影响，不需要数据恢复。
