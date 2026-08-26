# PROJECT1 知识库页面 UI 精细化收口证据

## 结论

`PASS`。知识库页面已改为自然纵向页面流，标题与工具栏收敛为 56px 的完全不透明 Sticky PageHeader，主文档表与右侧状态区保持主工作区结构，底部 QA、Top 5 结果与 AI 整理答案均可通过页面下滑访问。指定黄色“检索服务暂不可用”提示块已移除；真实状态文字、状态卡片和后端返回口径仍保留。

## 修改范围

- `frontend/src/pages/knowledge/KnowledgeBasePage.tsx`
- `frontend/src/pages/knowledge/knowledge-base-layout.css`
- `frontend/tests/knowledgeBaseLayoutContracts.test.mjs`
- 本证据目录与 `docs/codex/TASK_STATUS.md`

未修改后端、API、数据库、迁移、RAG、上传、检索、路由、RBAC、权限判断、加载态、禁用态或业务状态逻辑。

## 结构验收

- 标题：`知识库 / 业务知识库`，标题、知识范围和现有操作收敛为统一工具栏。
- Sticky：中段滚动 460px 后标题仍位于内容滚动区顶部；背景 `rgb(255,255,255)`，`isolation:isolate`，正文不穿透。
- 页面流：唯一滚动责任仍由 `.content-shell` 承担；页面根节点 `height:auto`、`overflow:visible`。
- 文档表：保留 6 列、分页和全部操作；长文件名与分类为省略显示并提供 Tooltip/title，时间列稳定，窄屏由表格内部横向滚动兜底。
- 下半区：QA、检索结果和 AI 答案可滚动到达；页面末尾与浮动 AI 入口垂直间距 111.625px，无遮挡。
- 右侧状态：索引摘要、RAG 状态、知识版本及现有版本操作保持不变；仅删除指定黄色提示块。

## 功能入口对照

详见 `CONTROL_ENTRY_COMPARISON.json`：修改前后均为 11 个 JSX Button、14 个 click 绑定、1 个上传绑定、7 个 API/搜索调用；8 个异步处理函数源码 SHA-256 逐段一致。删除项仅为 1 个指定黄色提示块。

## 浏览器点验

- URL：`http://127.0.0.1:5178/#/knowledge/knowledge-docs`
- 视口：1280×720（比参考桌面图更窄，用于非全屏兜底验证）
- 真实页面数据：83 份资料、79 份列表数据、8,339 chunks、门禁 9/9。
- 文档详情抽屉：PASS。
- 分页第 2 页：PASS，首行更新为 `AI-项目进展与分析 (10).docx`。
- QA 输入编辑并恢复：PASS；检索按钮保持启用。
- 全局 AI 悬浮入口打开/收起：PASS。
- 页面错误提示：0；知识库加载错误提示：0；Vite HMR/编译错误：0。

## 自动化验证

- `node --test tests/knowledgeBaseLayoutContracts.test.mjs`：4/4 PASS。
- `npm run unit`：57/57 PASS。
- `npm run lint`：TypeScript PASS，UI Shell 12/12 PASS。
- `npm run build`：PASS，3,689 modules transformed，KnowledgeBase 独立 CSS/JS chunk 生成成功。
- `git diff --check`：PASS（仅 Git 换行提示，无空白错误）。

## 截图

- `user_reference_before_after.png`：用户提供的优化标注基准。
- `after_top_1280x720.png`：最终首屏。
- `after_sticky_1280x720.png`：中段滚动后的 Sticky 标题与底部工作区。
- `after_bottom_1280x720.png`：页面末尾 QA / 结果 / AI 答案及悬浮入口安全区。

## 风险与边界

- 当前真实后端仍报告 RAG `未发布`、检索服务 `暂不可用`；本任务按要求只移除黄色提示块，不伪造可用状态、不更改检索逻辑。
- 浏览器使用现有 `frontend-development-reader` 身份；受 RBAC 保护的写操作按原权限隐藏。源码入口计数、API 调用和 8 个处理函数逐段哈希证明权限与功能逻辑未改。
- 数据库影响：0；业务写入：0；模型/RAG/发布状态变更：0。
