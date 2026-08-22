# Real provider smoke（无凭据、无回答全文）

| Provider/场景 | 结果 | 摘要 |
|---|---|---|
| MiMo 普通文本（最低调用） | REMOTE_BLOCKED | empty_response |
| MiMo 普通文本（一次诊断） | PASS | 7316.9 ms；input 256 / output 192 |
| MiMo 图片/截图 | REMOTE_BLOCKED | empty_response |
| DeepSeek 复杂文本 | PASS | 2766 ms；input 107 / output 91 |
| DeepSeek AnalysisPlan | REMOTE_BLOCKED | structured_response_schema_mismatch；一次正式 Planner 诊断仍未通过 |
| Kimi Premium（显式确认） | PASS | 3470 ms；input 40 / output 49 |

Kimi 未确认调用 0，静默 Premium 使用 0。除两次明确失败诊断外无重复调用。API Key 仅检查“是否配置”，从未打印或落盘。
