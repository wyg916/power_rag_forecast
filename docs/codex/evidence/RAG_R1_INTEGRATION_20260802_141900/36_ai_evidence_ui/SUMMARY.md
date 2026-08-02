# RAG-R1 AI 证据 UI 收口

## 结论

本原子包 PASS，仍为未发布状态。AI 助手三栏页面已消费主问答契约中的 `claims`、`citations`、`grounding_status` 与 `refusal_reason`，并在普通用户视图中形成业务化、fail-closed 的证据展示。

## 实现

- 只展示与 Claim 实际绑定的 Citation；未绑定、缺字段或不可用的引用不进入普通用户证据栏。
- Citation 仅展示业务化标题、章节/页码、原文摘录、相关度与绑定主张数；不展示内部 citation/release/trace 标识。
- `grounded`、`tool_grounded`、`tool_and_rag_grounded`、`unavailable/refused` 与 `not_required` 均有明确业务状态。
- `release_unavailable`、无证据、安全隔离及 Claim/Citation 校验失败均转换为业务可理解的拒绝原因。
- 普通用户警告二次净化，不展示模型名、密钥配置、路径、堆栈或内部诊断；授权开发者抽屉仍保留原始诊断能力。
- 修复回答复制按钮无障碍标签与 Ant Design 静态消息警告。
- 右侧建议动作改为 2×2 紧凑网格，知识引用空态压缩；1366×768 与 1672×941 四项操作全部可见。

## 验收

- 定向回归：14 passed。
- TypeScript + Vite：3675 modules，PASS。
- 浏览器：1920、1672、1440、1366、默认 1280 五档均无页面或工作区横向溢出。
- 真实本地知识问答：`知识证据暂不可用`，Citation 0；普通用户未看到模型/密钥/路径/Trace/内部 ID。
- 最终新标签页控制台 error/warn：0。
- 受限数据库只读复核：`beta10d_forecast_login`；`RAG-R1 candidate/is_current=false`；三张 RAG 审计表计数仍为 `[0,0,2]`，持久写入 0。
- Qdrant alias、snapshot、Published 和生产切换：0。

## 证据

- [最终 fail-closed 页面 1672×941](screenshots/ai_1672x941.png)
- [最终动作可见性 1366×768](screenshots/ai_actions_1366x768.png)
- [浏览器结构化结果](browser.json)
- [测试与数据库复核](tests.json)
- [写前检查点](pre_write/SUMMARY.md)

## 回滚

回退本原子提交即可恢复 UI；本包未执行数据库、Qdrant、Release、alias 或 snapshot 变更，无数据恢复步骤。

## 后续

知识库治理 UI、全量 RAG/AI 评测、snapshot、受控发布、alias 切换及回滚演练仍待后续独立原子包执行。
