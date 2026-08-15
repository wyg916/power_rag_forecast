# 基线、检查点与范围

## 只读基线

- 冻结路径：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`
- Release 分支：`release/beta10d-agent-rc-20260807`
- Release SHA：`1f4f7e50e3177aec21594b52ce74cd03dd77ea7d`
- 功能基线 SHA：`3a5ee83adbe7b791aac9826d83d9f9f886a5ded1`
- 一键启动：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807\run_project.bat`
- 候选工作树：`E:\智能运营分析项目_worktrees\ui_forecast_center_fidelity_20260814`
- 候选分支：`codex/ui-forecast-center-fidelity-20260814`
- 前置检查点：`E:\智能运营分析项目_worktrees\_checkpoints\forecast_center_bottom_space_fonts_20260815_pre`

检查点保存了 Git 状态、diff、未跟踪文件、修改文件、关键文件哈希、数据库影响和回滚说明。数据库影响为 0。

## 视觉输入

- 已实际读取 Figma 文件 `SCO0czpBdYglv3NAuwo22L` 的节点 `2:2`、`3:2`、`4:2`。
- 已读取三张 1672×941 参考图和用户最新截图反馈。
- 已定向读取两份项目源 Word 文档中预测中心 24 小时、历史对比和模型评估相关章节。

## 允许修改

- `frontend/src/components/forecast/ForecastDesign.tsx`
- `frontend/src/styles.css`
- 本任务证据与 `docs/codex/TASK_STATUS.md`

## 禁止修改

- 左侧导航、全局 Header、BasicLayout、全局主题和其他页面视觉。
- 后端、API 契约、数据库结构/数据、模型状态、Golden Set、RAG 状态、权限体系和生产配置。
- 冻结 Release、Tag、远端分支和 production alias。

## 回滚

- 候选源代码提交可通过 `git revert 91644ca` 回滚。
- 未集成到 Release，冻结项目无需回滚。
- 数据库、模型和 RAG 均无写入或迁移。
