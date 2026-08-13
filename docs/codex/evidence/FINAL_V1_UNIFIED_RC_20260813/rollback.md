# Rollback

- ff-only 收敛前 Release SHA：`fefb72f6c56e387a10bd2a4d798813593f1f2334`。
- 完整 E 盘 Git bundle 与检查点位于：`E:\智能运营分析项目\.codex_tmp\release-governance-20260813\20260813_044500_FINAL_V1_UNIFIED_RC_PRE`。
- 本任务未执行数据库迁移、业务写入、模型激活、RAG 发布或 production alias 切换，无数据回滚需求。
- 如确需回退 Release 引用，须先停止并确认没有工作树使用者，再按检查点 `RESTORE.md` 的显式 `update-ref` 命令人工执行；不得使用 destructive reset。
