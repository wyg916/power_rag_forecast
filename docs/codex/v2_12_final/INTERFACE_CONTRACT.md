# 项目一 v2.12.0 接口契约冻结

## 1. 契约地位

本文冻结 A/B/C 并行期间的目标契约。标注为“目标”的字段或 endpoint 不等于 v2.11.2 已实现；C 负责后端收敛，B 只按本契约实现 client/type，A 不修改 AI/RBAC 契约。任何不兼容变更只能由 Final Integration 更新本文并记录迁移策略。

统一约束：UTF-8、JSON 字段使用 `snake_case`、时间使用带时区 ISO 8601、ID 为服务端生成的不透明字符串。响应不得包含密码、Token、完整 DSN、内部堆栈或隐藏权限数据。

## 2. 通用请求与响应

### 2.1 通用请求元数据

```json
{
  "request_id": "req_<opaque>",
  "session_id": "sess_<opaque>",
  "run_id": "run_<opaque_or_null>",
  "trace_id": "trace_<opaque_or_null>"
}
```

- `request_id`：每次请求唯一；客户端可提供，服务端必须校验或生成。
- `session_id`：由已认证用户拥有，会话读取/更新/删除必须复核 user/tenant。
- `run_id`：涉及数据、预测、策略、报告或工具调用时贯通事实链；纯文本问答可为空。
- `trace_id`：服务端生成并贯穿路由、Provider、工具、附件和 Citation。

### 2.2 非流式成功响应

```json
{
  "success": true,
  "request_id": "req_<opaque>",
  "session_id": "sess_<opaque>",
  "run_id": null,
  "trace_id": "trace_<opaque>",
  "status": "completed",
  "answer": {"markdown": "..."},
  "citations": [],
  "route": {},
  "usage": {},
  "warnings": []
}
```

只有回答或受控工具结果真实完成时才能返回 `success=true` 和 `status=completed`。空字符串、历史答案、固定模板、未执行的工具、解析失败后的空附件或 Provider 错误不得包装成成功。

### 2.3 统一失败响应

```json
{
  "success": false,
  "request_id": "req_<opaque>",
  "trace_id": "trace_<opaque>",
  "status": "failed",
  "error": {
    "code": "ATTACHMENT_PARSE_FAILED",
    "message": "附件解析失败，请重试或更换文件。",
    "retryable": true,
    "details": {}
  }
}
```

`details` 只能包含面向调用方的安全字段，不得泄露 Provider 原始密钥、完整输入、SQL、内部路径或堆栈。

## 3. AI 对话与流式回答

### 3.1 目标 endpoint

- 非流式：`POST /api/ai/chat`
- 流式：`POST /api/ai/chat/stream`，响应 `text/event-stream`
- 会话：沿用 `/api/ai/chat/sessions` 与 `/api/ai/chat/sessions/{session_id}`
- 中止：以服务端支持的 cancel endpoint 或流连接中止实现；必须关联 `request_id`/`trace_id`，不得仅在前端隐藏输出。

### 3.2 ChatRequest

```json
{
  "request_id": "req_<opaque>",
  "session_id": "sess_<opaque_or_null>",
  "message": "用户问题",
  "mode": "general|chatbi|rag|file|vision",
  "stream": true,
  "requested_tier": "standard|premium",
  "attachment_ids": ["att_<opaque>"],
  "page_context": null,
  "knowledge_scope": "none|authorized_enterprise|attachments|authorized_enterprise_and_attachments"
}
```

- `message` 必须有长度上限并做安全规范化，但不能把附件内容当系统指令。
- `requested_tier=premium` 必须来自用户明示动作；前端不得默认选中，后端不得静默改写。
- `attachment_ids` 只允许当前用户/tenant/session 的 `ready` 附件。
- `knowledge_scope` 必须显式；会话附件不得自动写入企业知识库。

### 3.3 ChatResponse

除通用字段外至少包含：

```json
{
  "answer": {
    "markdown": "自然回答",
    "intent": "direct|data_analysis|knowledge|file_reading|vision|action_advice",
    "result_dataset_id": null,
    "grounded": true
  },
  "citations": [],
  "attachment_citations": [],
  "route": {
    "requested_tier": "standard",
    "logical_alias": "GENERAL_DEFAULT",
    "selected_provider": "mimo",
    "selected_model": "<configured-model-id>",
    "route_reason": "general_low_cost",
    "fallback_used": false,
    "fallback_from": null,
    "fallback_reason": null
  },
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "latency_ms": 0,
    "estimated_cost": 0,
    "currency": "<configured>"
  }
}
```

业务数值必须来自受控 Result Dataset/业务 API；知识结论必须有可校验 Citation；文件结论必须有附件来源。无证据时 `grounded=false` 并返回明确的无证据语义，不能编造。

### 3.4 SSE 事件

允许事件：`meta`、`status`、`delta`、`citation`、`attachment_citation`、`tool_status`、`error`、`done`。

- 首个 `meta` 含 request/session/trace 和选路摘要。
- `delta` 只含本次新增文本，不重复全量答案。
- `error` 后不得再发送成功 `done`。
- `done` 必须含最终 usage、route、citation 数量和 `status=completed|cancelled|failed`。
- 客户端断开或用户取消后，服务端应取消尚未开始/可取消的 Provider 与工具调用，并记录 `cancelled`。

## 4. 附件上传、解析、删除、绑定与引用

### 4.1 目标 endpoint

- `POST /api/ai/attachments`：multipart 上传，返回附件记录。
- `GET /api/ai/attachments/{attachment_id}`：查询 `uploading|parsing|ready|failed|cancelled|deleted`。
- `DELETE /api/ai/attachments/{attachment_id}`：当前所有者删除/取消，幂等返回终态。
- 对话通过 `attachment_ids` 绑定，不允许仅凭文件名或客户端路径绑定。

### 4.2 AttachmentRecord

```json
{
  "attachment_id": "att_<opaque>",
  "session_id": "sess_<opaque>",
  "file_name": "safe-display-name.ext",
  "media_type": "application/pdf",
  "size_bytes": 0,
  "sha256": "<hex>",
  "status": "parsing",
  "parser": "<name_or_null>",
  "created_at": "<iso8601>",
  "expires_at": "<iso8601>",
  "error": null
}
```

支持白名单：PNG/JPG/JPEG/WEBP、PDF、DOCX、TXT、MD、XLSX、CSV。必须校验扩展名、真实 MIME、大小、数量、页数/行数、压缩炸弹/恶意文件、宏与公式注入；禁止执行附件内容。解析失败保持 `failed`，不得以空文本进入 `ready`。

附件默认 `session-scoped`、临时 TTL、用户/tenant 隔离，不自动进入正式知识库。删除后后续回答不得继续使用；清理任务必须可审计且不影响其他会话。

### 4.3 附件引用

```json
{
  "citation_id": "acit_<opaque>",
  "attachment_id": "att_<opaque>",
  "file_name": "safe-display-name.ext",
  "location": {"page": 3, "sheet": null, "section": "2.1", "row_range": null},
  "quote": "受长度限制的证据摘要",
  "chunk_id": "achunk_<opaque>"
}
```

页/Sheet/区段/行范围按文件类型提供；无法定位时字段为空并明确说明。引用不得暴露其他用户附件、原始磁盘路径或隐藏数据。

## 5. 当前页面上下文与权限边界

### 5.1 PageContext

```json
{
  "route_key": "forecast.overview",
  "page_title": "预测中心",
  "active_filters": {},
  "selected_entity": {"type": "forecast_run", "id": "run_<opaque>"},
  "visible_summary": {},
  "permission_snapshot_hash": "<opaque>"
}
```

仅允许上述结构化字段。禁止发送完整 DOM、隐藏字段、Token、完整数据表、未授权 ID 或技术调试信息。用户可关闭页面上下文；前端权限判断不能替代后端复核。后端必须按当前身份/tenant 重新校验 route、entity、filter 和引用对象，忽略客户端声称但无权访问的 capability。

## 6. capability/permission manifest

以现有 `GET /api/security/me` 或兼容的当前用户 endpoint 扩展返回目标 `capability_manifest`；若最终采用新 endpoint，必须由 Final Integration 同步更新契约和 B/C。

```json
{
  "user_id": "<opaque>",
  "tenant_id": "<opaque>",
  "roles": ["analyst"],
  "permissions": ["dashboard:read"],
  "capability_manifest": {
    "routes": {"dashboard": true, "settings": false},
    "actions": {"forecast.run": true, "settings.write": false},
    "generated_at": "<iso8601>",
    "policy_version": "v2.12.0"
  }
}
```

判断口径：

- 菜单：route capability 为 false 时不生成入口。
- 路由：直接 URL 仍经前端守卫和后端接口授权；整页无权限显示友好 Forbidden。
- Tab/卡片：所需数据 capability 缺失时不请求接口，默认隐藏或显示单个轻量占位。
- 按钮：action capability 缺失时不显示；因业务状态禁用与因权限隐藏必须区分。
- 后端逐 endpoint 继续依据 `API_PERMISSION_MATRIX.csv` 与当前策略强制 RBAC；manifest 只是前端体验提示，不是授权令牌。
- 403 使用统一业务错误，不向业务用户堆叠权限码或内部堆栈；trace/audit 仍记录安全上下文。

## 7. 五个逻辑模型别名与三 Provider 路由

| 逻辑别名 | 默认 Provider | 用途 | 约束 |
|---|---|---|---|
| `GENERAL_DEFAULT` | MiMo | 低成本通用问答、摘要、普通解释 | 标准 tier |
| `VISION_DEFAULT` | MiMo | 截图、图片、图表理解 | 只描述可见证据，不猜不可见数值 |
| `DATA_PLANNER` | DeepSeek | ChatBI/NL2SQL 结构化规划 | 仅输出 `AnalysisPlan` |
| `COMPLEX_REASONER` | DeepSeek | 复杂文本推理、受控工具规划 | 工具仍由确定性策略执行 |
| `PREMIUM` | Kimi | 超长文档、跨文档综合、深度管理报告 | 用户明示选择/确认 |

业务代码只引用逻辑别名，不把具体模型名散落在业务分支。具体 model id 来自 Git 忽略的本地配置或受控配置服务，响应仅返回安全的 model 标识。

路由规则：

1. 首先依据任务能力选择逻辑别名，再解析 Provider/model。
2. MiMo 服务失败可最多一次受控同级/DeepSeek fallback；必须记录原因。
3. DeepSeek 低置信度或超长上下文只能提示用户选择 Premium，不得静默调用 Kimi。
4. Kimi 仅用于 `requested_tier=premium` 且用户已明示；不得作为无感知 fallback。
5. 429、timeout、5xx、invalid output、cancel 和 capability mismatch 使用不同错误码。
6. 最多一次 retry 和一次受控 fallback；不得无限重试。

## 8. ChatBI AnalysisPlan 安全契约

LLM 只能输出结构化 `AnalysisPlan`，示例字段：

```json
{
  "analysis_plan_id": "plan_<opaque>",
  "dataset_id": "<allowlisted>",
  "metrics": ["<catalog_metric_id>"],
  "dimensions": ["<catalog_dimension_id>"],
  "filters": [],
  "time_range": {},
  "comparison": null,
  "sort": [],
  "limit": 100
}
```

确定性 validator 必须校验用户/tenant、dataset、字段、指标、维度、join、过滤、时间、排序和行数；SQLAlchemy 编译器使用绑定参数生成查询；只有受控执行器可访问 PostgreSQL。LLM 直接生成并执行任意 SQL、绕过 catalog、执行写 SQL 或静默扩展权限均禁止。最终数字与图表必须来自同一 Result Dataset，并记录 `result_dataset_id`/`result_hash`。

## 9. Trace、成本与 Citation 字段

每次模型调用/工具调用至少记录：

- `request_id`、`session_id`、`run_id`、`trace_id`
- `requested_tier`、`logical_alias`、`selected_provider`、`selected_model`
- `route_reason`、`fallback_used`、`fallback_from`、`fallback_reason`
- `attachment_ids`、`page_context_used`
- `input_tokens`、`output_tokens`、`latency_ms`、`estimated_cost`、`currency`
- `citations`、`attachment_citations`、`result_dataset_id`、`result_hash`
- `status`、`error_code`、`created_at`

Trace 读取使用现有 `trace:read` 权限；普通用户只能看到自己的安全摘要，管理员/开发者也不得获取密钥或完整敏感正文。

## 10. 明确失败语义

| 场景 | HTTP/流状态 | 业务错误码 | 规则 |
|---|---|---|---|
| 未认证 | 401 | `AUTH_REQUIRED` | 不泄露资源存在性 |
| 无权限/跨租户 | 403 | `PERMISSION_DENIED` | 不返回隐藏数据；前端友好展示 |
| 附件过大 | 413 | `ATTACHMENT_TOO_LARGE` | 不进入解析 |
| 类型不支持 | 415 | `ATTACHMENT_TYPE_UNSUPPORTED` | 明确白名单 |
| 参数/AnalysisPlan 无效 | 422 | `VALIDATION_FAILED` / `ANALYSIS_PLAN_REJECTED` | fail-closed |
| 证据不足 | 424 或受控 422 | `EVIDENCE_NOT_FOUND` | 不编造结论 |
| 附件解析失败 | 424 | `ATTACHMENT_PARSE_FAILED` | 不把空内容当 ready |
| Provider 限流 | 429 | `PROVIDER_RATE_LIMITED` | 遵守最多一次受控回退 |
| Provider 无效响应 | 502 | `PROVIDER_INVALID_RESPONSE` | 不返回历史/固定答案 |
| Provider 不可用 | 503 | `PROVIDER_UNAVAILABLE` | 明确 retryable |
| Provider 超时 | 504 | `PROVIDER_TIMEOUT` | 记录实际状态 |
| 用户取消 | 流 `cancelled` | `REQUEST_CANCELLED` | 不再发送 completed |

## 11. 禁止假成功

以下任一行为均违反冻结契约：

- 解析失败后用空文本继续回答并返回 success。
- Provider/工具失败后返回固定模板、历史结果、Mock 或缓存旧答案且不标明失败。
- 无权限数据被前端隐藏但仍由后端返回或被 AI 检索。
- 无证据时伪造 Citation、附件页码、业务数值、任务 SUCCESS 或成本。
- Premium 静默升级、无限 retry/fallback，或省略 route/fallback 记录。
- LLM 直接生成并执行任意 SQL。

任何实现偏离本文时，任务状态必须为 PARTIAL/FAIL，并在交付中列出差异；不得通过弱化测试或更改错误语义获得 PASS。
