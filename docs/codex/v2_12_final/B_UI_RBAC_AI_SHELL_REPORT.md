# PROJECT1 v2.12.0 B：全站 UI、RBAC 与全局 AI Shell 报告

## 结论

PROJECT1_V2_12_B_UI_RBAC_GLOBAL_AI_SHELL 前端实现与验证完成，状态为 PASS_WITH_INTEGRATION_DEPENDENCY。32/32 业务路由在四档视口共 128/128 组合通过 UI Shell 验收；权限菜单、路由、子页、模块、动作及请求前置门禁均按 API_PERMISSION_MATRIX.csv 收口；全局 AI Drawer、跨页状态、页面上下文、多模态附件与动态回答渲染已完成。前端可进入集成，但附件完整 ready 流程依赖后端补齐冻结契约中的 GET/DELETE 接口。

## 修改范围

- 统一设计基础：字号、4/8/12/16/24/32 间距、36–40px 控件、Card/Panel/Alert/状态视图和 Sticky Page Header。
- 页面收口：32 个业务路由统一标题/工具区；默认标题区不再渲染说明性副标题；业务主视图隐藏技术追溯元数据，原字段和审计能力未删除。
- 权限体验：新增 PermissionRoute、PermissionGate、Can、ActionGuard、FullPageForbidden、SectionUnavailable，菜单、Tab、模块、按钮及已知无权限请求统一门禁；后端 403 继续兜底并转为友好文案。
- 全局 AI Shell：登录后在 BasicLayout 全局挂载 52px 悬浮入口与 500px 右侧 Drawer；支持新会话、关闭、收起、停止生成和完整页跳转。
- 跨页状态：外置 store 加 sessionStorage 保存会话、消息、流式状态、草稿、附件和关联当前页面开关；只有主动新建会话才清空。
- 页面上下文：只发送 route_key、page_title、active_filters、selected_entity、visible_summary 和权限快照摘要，不读取 DOM、隐藏字段、Token 或密钥。
- 多模态附件：文件选择、拖拽、Ctrl+V；支持 PNG/JPG/JPEG/WEBP/PDF/DOCX/TXT/MD/XLSX/CSV；统一缩略图、uploading/parsing/ready/failed、删除和重试；仅 ready 附件进入问答上下文。
- 动态回答：按可选响应结构渲染 Markdown、表格、引用、文件来源、复制、反馈、继续追问与停止生成，不强制机械化固定章节。

## 权限与安全边界

- 权限来源：docs/codex/security/API_PERMISSION_MATRIX.csv 与冻结 INTERFACE_CONTRACT.md。
- 未按角色中文名称猜测权限；管理员通配能力保持。
- 已知无权限接口在前端不发请求，后端 403 防线未被移除。
- 前端隐藏仅影响默认业务视图；追溯字段、API 契约与审计详情能力均保留。
- 未发送完整 DOM、隐藏数据、未授权数据、Token、密钥或内部流水线字段。

## 验证结果

| 项目 | 结果 |
|---|---|
| UI 路由 | PASS，32/32 |
| 四视口 | PASS，128/128 路由-视口组合 |
| Sticky Header | PASS，128/128 |
| 页面副标题可见数 | 0 |
| 默认技术元数据块 | 0 |
| Raw 403 可见数 | 0 |
| 正常路由 smoke 请求失败 | 0 |
| Console / 页面错误 | 0 / 0 |
| 全局 AI 悬浮入口 | PASS，32/32 |
| Drawer 跨页状态 | PASS |
| Ctrl+V 图片 | PASS，浏览器真实 File |
| 拖拽 | PASS，自动化契约覆盖 |
| lint | PASS，UI 契约 6/6 |
| unit | PASS，22/22 |
| typecheck | PASS |
| build | PASS，3682 modules |

## 集成依赖与风险

唯一已知集成依赖：当前后端仅实现 POST /api/ai/attachments；冻结契约要求的 GET /api/ai/attachments/{id} 和 DELETE /api/ai/attachments/{id} 尚不可用。浏览器实测上传 POST 成功、GET 轮询返回 404；前端正确进入 failed 并提供重试/删除，没有伪造 ready。后端补齐后需执行一次附件 uploading → parsing → ready、问答引用及删除的集成回归。

本任务未修改 backend/、prediction_engine/、model_ops/、migrations/、运行脚本、CI、main 或其他并行分支。

## 回滚

本任务为单提交前端与文档改动。需要回滚时，在集成分支对最终提交执行普通 git revert FINAL_SHA；不需要数据库回滚，数据库影响为 0。

## 证据

- docs/codex/evidence/B_ui/PROJECT1_V2_12_B_20260822_191034/preflight.md
- docs/codex/evidence/B_ui/PROJECT1_V2_12_B_20260822_191034/test-results.md
- docs/codex/evidence/B_ui/PROJECT1_V2_12_B_20260822_191034/route-matrix.md
- docs/codex/evidence/B_ui/PROJECT1_V2_12_B_20260822_191034/browser-acceptance.md
