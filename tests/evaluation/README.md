# AI助手固定评测集

本目录用于评测 AI 助手在默认模式和 `debug=true` 模式下的回答、RAG 命中、工具调用和调试字段隐藏情况。

## 文件说明

| 文件 | 说明 |
|---|---|
| `ai_assistant_eval_questions.json` | 固定评测题库，共 100 条，覆盖电价预测、负荷天气、尖峰风险、模型解释、交易策略、系统使用和日常问答。 |
| `rag_expected_hits.json` | RAG 命中文档辅助期望配置，会与题库中的 `expected_titles_any` 合并使用。 |
| `run_ai_assistant_eval.py` | 自动化评测脚本，调用 `/api/ai/chat` 并输出 JSON/Markdown 报告。 |
| `output/` | 评测报告输出目录。 |

## 运行方式

后端未启动时先启动：

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

运行评测：

```bash
python tests/evaluation/run_ai_assistant_eval.py --base-url http://127.0.0.1:8001 --model-provider auto
```

脚本默认会为每条问题调用一次默认模式和一次 `debug=true` 模式，并生成：

```text
tests/evaluation/output/baseline_hash_heuristic_report.json
tests/evaluation/output/baseline_hash_heuristic_report.md
```

后续接入 BGE embedding 或 reranker 后，脚本会根据调试返回的 provider 信息自动生成对应报告名，也可以用 `--report-name` 显式指定。

## 评测重点

1. 专业问题是否触发 RAG；
2. 日常问题是否避免强行套用专业模板；
3. Top-K 证据是否命中预期知识库标题或关键词；
4. 默认响应是否隐藏 `trace`、`tools`、`tool_calls`、`workflow`、`agent_trace`、`trace_id` 等调试字段；
5. `debug=true` 是否返回 RAG、意图、工具和 trace 明细；
6. 回答中是否出现固定调试模板或无法回答类禁用表达。
