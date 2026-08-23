# DeepSeek `empty_response` 离线根因诊断

## 1. 结论

`DEEPSEEK_EMPTY_RESPONSE_CLASSIFICATION=G_MODEL_ENDPOINT_CAPABILITY_MISMATCH`

上一轮成本受控脚本绕过 `DATA_PLANNER` 能力注册表，直接调用 `DeepSeekProvider.complete()`，因此实际请求使用 Provider 默认值 `deepseek-v4-flash`。当前 Integration 本地配置和此前真实 PASS 证据均表明，受控 `DATA_PLANNER` 路由应向 DeepSeek OpenAI-compatible endpoint 发送 `deepseek-chat`：

- 当前 `.env`：`DEEPSEEK_MODEL=deepseek-chat`；
- 2026-08-22 的真实 PASS 证据：业务元数据保留产品稳定标识 `deepseek-v4-flash`，但脱敏请求诊断中的实际 `model` 为 `deepseek-chat`；
- 2026-08-23 的失败脚本：未显式传入能力注册表解析出的 model，失败证据中的 selected model 为 `deepseek-v4-flash`。

因此可以确认“定向验证没有复用正式能力路由、向端点发送了错误层级的模型标识”。修复后唯一一次真实调用使用 `deepseek-chat` endpoint alias 并完整通过，完成了因果闭环；没有使用历史响应代替当前验证。

另有独立的观测缺口：上一版 smoke 只投影了异常顶层字段，丢弃了 Adapter 已生成的嵌套脱敏诊断。该问题归入 `H_OTHER_WITH_EVIDENCE`，解释为什么无法从已落盘证据恢复精确 2xx 状态码、request ID、choices/message/reasoning/finish_reason/usage，但它不是模型空响应本身的根因。

## 2. 上一轮脱敏证据逐项核对

| 核对项 | 已确认结果 | 证据边界 |
|---|---|---|
| HTTP status | 成功 HTTP，精确 2xx 未保留 | Adapter 只在 `_request()` 成功且 `response.json()` 可解析后进入 `empty_response` 分支 |
| endpoint | `POST https://api.deepseek.com/chat/completions` | base URL 与 Adapter resource 可确认；不包含凭据 |
| selected provider | `deepseek` | 已落盘 |
| selected model | `deepseek-v4-flash` | 已落盘；这是绕过能力注册表后的 Provider 默认值 |
| request mode | non-stream | smoke 使用 `complete()`，payload 固定 `stream=false` |
| stream | `false` | 同上；不存在流聚合参与本次失败 |
| response_format | `{"type":"json_object"}` | smoke 调用参数可确认 |
| structured schema | Prompt 中包含当前 `AnalysisPlan` schema；HTTP 参数使用 `json_object` | 未向 Provider 声称原生 JSON Schema 能力 |
| request ID | 未保留 | 旧 smoke 异常投影缺陷 |
| response headers | 未保留 | 旧 smoke 异常投影缺陷 |
| response body | 存在且为可解析 JSON 对象 | 否则 Adapter 会产生 `invalid_response`，不会产生 `empty_response` |
| JSON 顶层字段 | 未保留 | 旧 smoke 异常投影缺陷 |
| choices 是否存在/数量 | 未保留 | Adapter 对缺少 choices 和空 content 都 fail-closed，旧投影无法区分 |
| message 是否存在 | 未保留 | 同上 |
| `message.content` | Adapter 归一化结果为空 | 非空字符串或受支持 multipart text 不会触发 `empty_response` |
| `reasoning_content` | 是否存在及长度未保留 | Adapter 会单独解析但不会把推理内容伪装成最终答案 |
| `tool_calls` | 无可执行 tool call | 非空 tool call 不会触发该分支 |
| finish reason | 未保留 | 旧 smoke 异常投影缺陷 |
| usage | 未保留 | 旧 smoke 写入的 0 是默认汇总值，不代表 Provider 实际返回 0 |
| provider error/message | 未发现 HTTP 错误；成功 body 内是否带 error 未保留 | 不能臆造 |
| 本地 Adapter 最终值 | `content=""`、`tool_calls=()`，结果为 fail-closed `empty_response` | 可由控制流确认 |

## 3. Adapter 与解析链检查

| 层级 | 结果 |
|---|---|
| Provider client | 非流式 `POST chat/completions`；HTTP 4xx/5xx、timeout、network 分开失败 |
| DeepSeek adapter | Provider 默认模型为产品稳定标识；正式业务请求必须由 capability registry 显式传入 endpoint model |
| response parser | 支持 string 和 multipart content；不会把空白、未知 part 或 reasoning-only 当成最终 content |
| stream aggregator | 本次请求 `stream=false`，排除 `E_STREAM_AGGREGATION_BUG` |
| JSON extractor | 支持纯 JSON 与 Markdown fence；缺少对象、malformed JSON 均 fail-closed |
| AnalysisPlan parser | Pydantic 严格校验，额外字段/错误类型不能伪装成功 |
| Frozen Schema validator | 解析后仍需执行语义目录、权限、字段、指标、维度、Join 和行数校验 |
| SQL 边界 | LLM 只产出 `AnalysisPlan`；任意 SQL 生成和执行仍为 0 |

没有证据支持伪造 content、默认 AnalysisPlan、历史结果 fallback 或跳过 schema validation。`reasoning_content` 即使存在也只作为脱敏形状诊断，不能晋升为最终业务输出。

## 4. 最小修复

1. 定向 DeepSeek smoke 通过 `resolve_capability(DATA_PLANNER)` 解析 provider/model，并显式把解析后的 endpoint model 传给 Adapter。
2. Adapter 脱敏诊断补齐 endpoint、request mode、stream、header 名称、body/字段存在性、choices/message/content/reasoning/tool-call 形状、finish reason、usage 状态、latency、response model 与 Adapter parse result。
3. smoke 对成功和异常使用相同的安全诊断投影；Provider 未返回 usage 时明确写 `USAGE_NOT_RETURNED_BY_PROVIDER`。
4. 离线 fixture 覆盖正常 JSON、Markdown fence、空 content、reasoning-only、malformed JSON、schema-invalid JSON、成功 HTTP 无 choices，以及流分片聚合；所有空响应路径保持失败关闭。

## 5. 真实复验判定

仅在 Adapter、AnalysisPlan、Frozen Schema、Semantic Catalog 和 Permission 本地测试全部通过后执行一次：

- 问题：`查询最近一天的平均日前价格。`
- `max_tokens<=400`
- `stream=false`
- 自动质量重试：0

只有 `HTTP_SUCCESS`、`NON_EMPTY_PROVIDER_RESPONSE`、`ADAPTER_PARSE`、`ANALYSIS_PLAN_SCHEMA_VALID` 和 `SEMANTIC_VALIDATION` 同时 PASS，才能关闭该阻断。若仍失败，使用本次完整脱敏结构确定精确类别并立即停止。

## 6. 唯一一次真实复验结果

| 字段 | 结果 |
|---|---|
| HTTP status | `200` |
| request ID | `2a105dbb-28bd-40c2-b9b9-5caf8cf2b323` |
| endpoint / mode | `chat/completions` / `non_stream` / `stream=false` |
| requested model | `deepseek-chat` |
| Provider response model | `deepseek-v4-flash` |
| response format | `json_object` |
| body / top-level fields | JSON object；`choices, created, id, model, object, system_fingerprint, usage` |
| choices / message | `1` / present |
| content | present，424 chars；正文未落盘 |
| reasoning / tool calls | reasoning absent；tool calls `0` |
| finish reason | `stop` |
| usage | `CAPTURED`；input 2480 / output 118 / total 2598 |
| latency | 2016.617 ms |
| Adapter parse | `PASS_CONTENT` |
| Frozen schema | `PASS` |
| Semantic validation | `PASS`，issue 0 |
| Raw SQL execution by LLM | `0` |

结论：`DEEPSEEK_REAL_ANALYSIS_PLAN=PASS`，`G_MODEL_ENDPOINT_CAPABILITY_MISMATCH` 已关闭。真实调用次数为 1，未重试。未配置准确单价，因此只报告 token 与调用次数，成本为 `PRICING_NOT_CONFIGURED`，不把缺少单价误记为零成本。

后续唯一一次 Attachment QA 返回 HTTP 200、`grounding_status=grounded`、input 2131 / output 196，但旧 evaluator 错把验收条件写成必须包含完整 `PROJECT_CODE=ALPHA-7281`，而冻结要求只需包含 `ALPHA-7281`；同时 `selected_attachment_citation` 被错误地复用了整体 `grounded` 布尔值，未单独保存 citation 命中结果。由于未保存回答正文和 citation 结构，现有证据无法离线重算实际结果。调用预算已用尽，未重试，因此 Targeted Gate 仍为 FAIL/NOT PROVEN。

该段保留的是上一轮真实调用的历史结论。用户随后仅为修复后的 evaluator 额外授权 1 次真实附件 QA；最新闭环结果见第 8 节，不回写或伪造上一轮证据。

## 7. 安全与回滚

- 不记录 API Key、Authorization、Prompt 全文、模型回答正文或完整 DSN。
- 本修复不生成默认计划、不放宽 RBAC、不改变 SQL 执行边界。
- 回滚可使用任务前增量检查点恢复相关文件；不对当前 Integration worktree 执行 reset 或 clean。

## 8. Attachment evaluator remediation 与一次授权复验

- evaluator 将 Grounding 与 Citation 拆分为两个独立布尔值，并分别保存答案事实命中、附件检索 chunk/source、Enterprise KB chunk、selected-only 模式以及 citation 的 attachment/file/source 映射。
- 完全本地 A–F fixture 覆盖：正确答案/正确引用、正确答案/无引用、错误答案/正确引用、错误答案/无引用、错误 attachment ID、Enterprise KB 冒充所选附件；六种组合全部按冻结预期判定。
- 测试附件为 1095 bytes TXT，唯一事实 `PROJECT_CODE=ALPHA-7281`，问题为“这个文件中的 PROJECT_CODE 是什么？”，knowledge scope 固定为 only selected attachments。
- 额外真实附件调用严格执行 1 次、自动 retry 0 次；input/output token 为 2145/233，服务端输出上限为 300。
- 真实结果：预期事实命中、附件检索 chunk 1、Enterprise KB chunk 0、Citation 1；citation 的 attachment ID、文件名和 source ID 均回溯到本次上传；`GROUNDING_PASS=true`、`CITATION_PASS=true`。
- 脱敏证据：`docs/codex/v2_12_final/evidence/attachment_real_qa_20260823_141859563.json`，SHA256 `6C8E1E5532E3AED369B62EF77A0AFBEA4D27A755AA05F3D21F0B8D84B789113C`。

结论：`ATTACHMENT_REAL_GROUNDING=PASS`、`ATTACHMENT_REAL_CITATION=PASS`、`FILE_QA_E2E=PASS`、`TARGETED_GATE=PASS`。专用 18085 实例已按来源证明关闭；没有触碰既有 8000/5173。
