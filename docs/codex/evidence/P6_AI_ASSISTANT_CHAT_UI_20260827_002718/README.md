# AI 助手 / 智能问答三栏工作台 UI 收口证据

- TASK：`PROJECT1_AI_ASSISTANT_CHAT_WORKSPACE_UI_LAYOUT_REFINEMENT`
- STATUS：`PASS`
- BASE_BRANCH：`main`
- BASE_SHA：`175712047a0abca6820010677003b724a160bd90`
- SCOPE：`FRONTEND_UI_ONLY_WITH_EXISTING_FUNCTION_PRESERVATION`
- BROWSER_ZOOM：`100%`（`visualViewport.scale=1`）

## 交付结果

- 共享 PageHeader 收为 56px，标题为“AI 助手 / 智能问答”，原“开发者信息”按钮及 Handler 进入同一视觉标题带。
- 1919×874 下工作区为 240px / 自适应中栏 / 320px 三栏，页面本身无横向或纵向多余滚动。
- 中栏使用消息区 `flex:1` 内部滚动，快捷问题与 Composer 固定在底部；Composer 完整可见。
- 左栏会话列表、右栏数据依据、关键指标摘要、相关知识与策略建议均拥有独立滚动责任；右栏外层不滚动。
- 1366px 与 1440px 下 5 个快捷问题改为 3+2 两行，完整文案不缩字、不截断；1919px 下保持单行。
- 长会话标题保留单行省略，并增加原生 `title` 查看完整内容。
- 数据依据列宽重新分配，字段和数据契约未改变。
- AI 悬浮入口保留原 Handler，右侧操作区预留 80px 安全区。

## 截图

- 修改前目标状态：`before_1919x874.png`
- 修改后目标状态：`after_1919x874.png`
- 修改后 1440×900：`after_1440x900.png`
- 修改后 1366×768：`after_1366x768.png`
- 1000×768、内容滚动 480px Sticky 门禁：`sticky_1000x768_scroll480.png`

## 功能入口保持

| 稳定页面级指标 | 修改前 | 修改后 |
|---|---:|---:|
| 可见按钮 | 31 | 31 |
| 可用按钮 | 29 | 29 |
| 禁用按钮 | 2 | 2 |
| 模式 Tab | 5 | 5 |
| 输入/选择入口 | 4 | 4 |
| 文件输入 | 2 | 2 |
| 常用问题 | 8 | 8 |
| 快捷问题 | 5 | 5 |
| Composer 按钮 | 4 | 4 |
| 右栏按钮 | 6 | 6 |

## 变更边界

`BACKEND_CHANGED=NO`

`API_CHANGED=NO`

`DATABASE_CHANGED=NO`

`MIGRATION_CHANGED=NO`

`RBAC_CHANGED=NO`

`BUSINESS_LOGIC_CHANGED=NO`

`AI_LOGIC_CHANGED=NO`

`PROMPT_CHANGED=NO`

`RAG_CHANGED=NO`

`AGENT_CHANGED=NO`

`EVENT_HANDLER_CHANGED=NO`

`EXISTING_FUNCTION_CHANGED=NO`

详见 `browser_metrics.json`、`test_summary.md`、`changed_files.txt`、`commands.txt` 和 `rollback.md`。
