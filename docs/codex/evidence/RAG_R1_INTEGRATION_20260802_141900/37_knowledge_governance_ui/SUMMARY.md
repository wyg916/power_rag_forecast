# 37 知识库版本治理与失败关闭 UI

## 结论

`PASS（未发布）`。知识库页面已接入真实企业 Release 公共投影，并把版本状态、准入语义、服务可用性、文档管理、检索 QA 和受权诊断收敛到同一工作台。真实 `RAG-R1` 仍为 `candidate/is_current=false`；无 Published 版本时页面明确显示“当前没有已发布版本”和“暂不可用”，不会将 Candidate 或空检索伪装为正常服务。

## 实现

- 新增 Release 列表、诊断、validate、publish、rollback 前端 API 边界；状态变更入口同时受 `knowledge:publish` 权限和二次确认保护。
- 普通页面移除数据库表名、`source_type`、Provider、模型路径等技术呈现；文档详情与检索片段详情均使用业务安全投影。
- 诊断接口只在 `knowledge:diagnose` 权限下由用户主动加载，默认不请求。
- 后端拒答块中的追溯术语在展示层映射为“可核验的知识依据”，后端审计契约不变。
- 低高度桌面视口改为纵向滚动工作台，文档列表不再被压缩为不可访问高度；普通桌面仍保持版本治理侧栏和检索工作区结构。

## 真实验收

- 真实 Release 投影：`RAG-R1 / 候选版本 / 待准入校验 / 当前没有已发布版本`。
- 真实 QA：0 条结果，展示“当前知识库没有达到相关度门槛且可核验的证据，无法据此回答该问题”。
- 普通页面技术字段扫描：0 命中；应用 console error/warn：0。
- 实际 in-app Browser 视口 `1280x720`（目标集合中的最窄、最低代表档）：document `1265x999`，水平溢出 false，工作台水平溢出 false。`1366x768` 使用同一低高度桌面分支；1440/1672/1920 使用无更紧最小宽度的桌面分支，并由 P6 响应式契约测试覆盖。
- 截图：`screenshots/knowledge_governance_1280x720.png`、`screenshots/knowledge_fail_closed_1280x720.png`。

## 数据与发布边界

- 浏览器未点击 validate/publish/rollback，未改变 Release 状态。
- 受限身份复核：`beta10d_forecast_login`；`kb_retrieval_runs=0`、`kb_citations=0`、`kb_rag_audit_events=2`，与 UI 前既有基线一致。
- `kb_search_results`、`kb_qa_tests` 对该受限角色不可读；QA 路由当前以 `record=False` 执行，本次未把只读检索写入测试事实表。
- Candidate、Qdrant alias、snapshot、Published、生产切换均未执行。

## 回滚

回退本任务独立提交即可恢复页面、前端 API 和样式；本任务没有数据库迁移或持久业务写入，不需要数据恢复。
