# B_UI 自动化验证证据

- 验证日期：2026-08-22
- 工作树：E:/智能运营分析项目_worktrees/project1_v2.12.0_ui_rbac_ai_shell
- 起始提交：3b6eb33df96ece08a60acce802d6ec249ec5a826
- 范围：仅 frontend/ 与本任务交付文档。

| 检查项 | 命令 | 结果 |
|---|---|---|
| 前端静态检查 | npm run lint | PASS；TypeScript 无报错，UI 源码契约 6/6 通过 |
| 前端单元测试 | npm run unit | PASS；22/22 通过 |
| 前端类型检查 | npm run typecheck | PASS |
| 前端生产构建 | npm run build | PASS；Vite 5.4.21，3682 modules transformed |
| 差异格式检查 | git diff --check | PASS |

## 最小自动化覆盖

- PermissionGate / Can / ActionGuard：权限显示、隐藏与 fallback 契约。
- PermissionRoute：路由及子页面权限矩阵、友好 Forbidden 契约。
- StickyPageHeader：sticky、字号与工具栏结构契约。
- AttachmentComposer：文件类型、拖拽、剪贴板、状态、失败重试和删除契约。
- GlobalAssistantDrawer：全局挂载、收起/关闭/新会话/停止/完整页、页面上下文契约。
- globalAssistantStore：会话、消息、草稿、附件和流式状态持久化契约。

## 说明

lint 使用仓库现有离线依赖组合：tsc --noEmit 加 UI 源码契约测试；本任务没有新增依赖，也没有修改锁文件。完整 22 项 Node 单元测试另由 npm run unit 执行。
