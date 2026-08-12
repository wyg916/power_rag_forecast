# Package 2 — Multi-Provider 适配层验收

- 基线提交：`9f3d2ea7ad0d808345dd4f5b6739435ac369c5cc`
- 状态：PARTIAL（代码与 DeepSeek 实测 PASS；Kimi/MiMo 缺 Key 阻塞实时验收）
- 变更规模：15 个文件，低于单包 20 文件限制；有效代码低于 1000 行。

## 已完成

1. 建立统一 `LLMProvider` 契约：`chat / chat_stream / structured_completion / tool_calls / health / capabilities`。
2. Kimi K2.6、MiMo V2.5、DeepSeek V4-Flash 共用 OpenAI-compatible 适配器；模型和 Base URL 按任务固定，真实 Key 只从环境变量读取。
3. 显式 Provider 失败不再静默换模型；AUTO 仅在 timeout、HTTP 429、HTTP 5xx 时按配置顺序回退，并记录实际 provider、model、fallback reason。
4. HTTP 400/401、响应契约错误、空响应不触发 AUTO 回退；用户响应只显示“所选模型当前不可用”，详细错误仅保留在受控 trace/debug 元数据。
5. `/api/model-gateway/health` 返回 configured/available/model/base URL/capabilities，不返回密钥；Chat、Agent、ChatBI、Gateway 输入统一限制为 `auto/kimi/mimo/deepseek/ollama`。
6. 新增独立真实探针脚本；输出只保存状态、长度、计数与延迟，不保存提示词之外的 Provider 回答正文或任何 Key。

## 测试

- 单元/受影响矩阵：`87 passed, 5 skipped, 1 deselected`。
- 5 个 skipped 均为既有 `isolated PostgreSQL gate only`。
- 1 个 deselected 为 `test_database_table_browser_endpoints_are_safe`：当前非隔离数据库环境返回 503，首次并跑中已复现，与 Provider 改动无关。
- Python compile：PASS。
- `git diff --check`：PASS。
- 敏感信息扫描仅命中既有脱敏/伪密钥测试样本，新增代码与证据无真实 Key。

## 真实 Provider 结果

| Provider | 模型 | 鉴权/Models | 中文 | 多轮 | 流式 | 结构化 | Tools | 并发2 | 结论 |
|---|---|---|---|---|---|---|---|---|---|
| Kimi | `kimi-k2.6` | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | BLOCKED_MISSING_KEY |
| MiMo | `mimo-v2.5` | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | 未执行 | BLOCKED_MISSING_KEY |
| DeepSeek | `deepseek-v4-flash` | PASS/可见 | PASS | PASS | PASS/2 chunks | PASS | PASS/1 call | PASS/2 | PASS |

DeepSeek 最终三 Provider 汇总探针总耗时 `13263.253 ms`，配置 timeout `120 s`，Key 仅记录不可逆短指纹；执行过程中出现过两次低 token 预算导致的空正文，调整为与推理模型匹配的 320 token 探针预算后全项通过，未改模型、未切 Provider。权威原始证据为 `provider_live_probe_final.json`；其余 `provider_live_probe*.json` 保留首轮和重试诊断历史，不作为最终通过依据。

## 边界与回滚

- 未执行数据库迁移/写入、业务模型 Active 切换、RAG alias 切换、生产发布或远程推送。
- 回滚：对 Package 2 独立提交执行 `git revert <package2_sha>`；无需数据库恢复。
