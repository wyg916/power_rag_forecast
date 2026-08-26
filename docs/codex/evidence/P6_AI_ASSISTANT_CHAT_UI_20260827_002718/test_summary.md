# 测试摘要

## 工程门禁

| Gate | 结果 |
|---|---|
| `git diff --check` | PASS |
| `npm.cmd run typecheck` | PASS |
| `npm.cmd run lint` | PASS，12/12 |
| `npm.cmd run unit` | PASS，53/53 |
| `npm.cmd run build` | PASS，3686 modules，25.36s |
| 主前端 `http://127.0.0.1:5173/` | HTTP 200 |
| QA 前端 `http://127.0.0.1:5176/` | HTTP 200 |
| 后端 `http://127.0.0.1:8000/health` | HTTP 200 |

## 浏览器门禁

| Gate | 结果 |
|---|---|
| PAGE_HORIZONTAL_SCROLL | 0 |
| UNNECESSARY_PAGE_VERTICAL_SCROLL | 0（1919、1440、1366） |
| PAGE_HEADER_BACKGROUND | OPAQUE，`rgb(246, 248, 251)` |
| STICKY_CONTENT_PENETRATION | 0；滚动 480px 后 Header y=60 不变 |
| CENTER_COMPOSER_FULLY_VISIBLE | PASS |
| QUICK_QUESTIONS_VISIBLE | PASS，1919 单行；1440/1366 为 3+2 两行 |
| RIGHT_DATA_PANEL_VISIBLE | PASS |
| RIGHT_METRIC_PANEL_USABLE | PASS，内部滚动 |
| LEFT_PANEL_USABLE | PASS |
| CHAT_INTERNAL_SCROLL | PASS，`overflow-y:auto` |
| RIGHT_RAIL_INTERNAL_SCROLL | PASS；三个 body 的实测 scrollTop 分别可达 182/342/267，页面 scrollTop 保持 0 |
| FLOATING_BUTTON_OCCLUSION | 0；操作区保留 80px 安全区 |
| FONT_READABILITY | PASS |
| FUNCTION_PRESERVATION | PASS，31→31 |
| Browser Console Error/Warning | 0/0 |
| Page Error | 0 |
| Unexpected Request Failure | 0 |
| Unexpected 4xx/5xx | 0 |

## 交互结果

- 5 个模式 Tab 逐一点击，激活态均正确。
- 搜索框接受并清空文本；新建对话清空 Composer 并出现成功提示。
- “换一批”后 8 个常用问题顺序发生预期轮换。
- 分析范围切换到“预测分析”，回答模式切换到“高阶模式（明确选择）”，页面重载后回到既有默认值。
- 导出弹窗、引用数据弹窗、开发者信息 Drawer、全局 AI Drawer 均可打开并关闭。
- 历史记录入口进入 `#/assistant/assistant-faq`，返回聊天路由正常。
- 上传附件与截图/图表均实际触发浏览器 file chooser。
- 本地 SSE 隔离环境中：1 个常用问题、5 个快捷问题、Composer 发送、4 个右栏动作全部收到完成响应。
- 未执行真实文件上传、真实导出下载或外部 AI Provider 调用。
