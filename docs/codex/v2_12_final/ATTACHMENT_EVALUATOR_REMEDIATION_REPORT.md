# PROJECT1 v2.12.0 Attachment Evaluator Remediation Report

## 判定

```text
STATUS=PASS
EVALUATOR_OFFLINE_TESTS=PASS_A_TO_F
ATTACHMENT_REAL_CALL_COUNT=1
ATTACHMENT_REAL_RETRY_COUNT=0
ATTACHMENT_REAL_GROUNDING=PASS
ATTACHMENT_REAL_CITATION=PASS
ATTACHMENT_RETRIEVED_CHUNKS=1
ATTACHMENT_ENTERPRISE_KB_CHUNKS=0
FILE_QA_E2E=PASS
TARGETED_GATE=PASS
```

## 可恢复检查点

- 起点 SHA：`edc5c0973e9fbff63748bdcc33845b387805ae5f`
- 检查点：`backups/phase3/20260823_140602185_ATTACHMENT_EVALUATOR_PRE/`
- 检查点 manifest SHA256：`0D69437C8505F8FA4DF12709399D949EE0411DDE0388F822864C9CBB1A3E33EB`
- 数据库影响：无 migration、无 schema 变更、无业务数据写入；仅上传并删除本次临时附件。

## Evaluator 独立证据契约

Evaluator 不再依赖一个 overall 布尔值，分别持久化：

- 附件 ID、文件名、问题、预期事实和脱敏回答片段；
- 回答是否包含预期事实；
- 所选附件 chunk 数量与 source ID；
- Enterprise KB chunk 数量和 only-selected 模式；
- 独立的 `GROUNDING_PASS`；
- citation 数量、attachment ID、文件名和 source ID；
- 独立的 `CITATION_PASS`。

Grounding 不依赖 citation，因此“正确答案 + 无 citation”保持 Grounding PASS / Citation FAIL。Citation 不依赖答案，因此“错误答案 + 正确 citation”保持 Grounding FAIL / Citation PASS。

## A–F 完全本地 fixture

| 用例 | Grounding | Citation | 结果 |
|---|---:|---:|---|
| A. 正确答案 + 正确 citation | PASS | PASS | PASS |
| B. 正确答案 + 无 citation | PASS | FAIL | PASS |
| C. 错误答案 + 正确 citation | FAIL | PASS | PASS |
| D. 错误答案 + 无 citation | FAIL | FAIL | PASS |
| E. 错误 attachment ID | PASS | FAIL | PASS |
| F. Enterprise KB 而非 selected attachment | FAIL | FAIL | PASS |

测试命令与结果：

- evaluator + 300-token 服务契约：`7 passed, 30 deselected`；
- 关联 AI、附件、RBAC 后端回归：`56 passed`；
- 前端 unit：`28/28 passed`；
- TypeScript/lint + UI shell：`10/10 passed`。

## 唯一一次真实附件 QA

| 字段 | 结果 |
|---|---|
| 文件 | 1095 bytes TXT；`alpha-7281.txt` |
| 唯一事实 | `PROJECT_CODE=ALPHA-7281` |
| 问题 | 这个文件中的 PROJECT_CODE 是什么？ |
| ONLY_SELECTED_ATTACHMENTS | YES |
| 调用 / retry | 1 / 0 |
| input / output token | 2145 / 233 |
| output token 上限 | 300 |
| ANSWER_CONTAINS_EXPECTED_FACT | YES |
| RETRIEVED_ATTACHMENT_CHUNK_COUNT | 1 |
| ENTERPRISE_KB_CHUNK_COUNT | 0 |
| CITATION_COUNT | 1 |
| attachment/file/source 回溯 | PASS |
| GROUNDING_PASS / CITATION_PASS | YES / YES |

脱敏证据：`docs/codex/v2_12_final/evidence/attachment_real_qa_20260823_141859563.json`；SHA256 `6C8E1E5532E3AED369B62EF77A0AFBEA4D27A755AA05F3D21F0B8D84B789113C`。证据不保存 API key、Authorization、完整 DSN 或附件原文。

## 改动范围审计

用户指定的原始 15 tracked + 2 untracked 改动全部属于以下白名单；本轮只新增 evaluator 报告和脱敏 JSON 证据：

| 白名单范围 | 文件 |
|---|---|
| RBAC fix | `backend/app/api/v1/endpoints/system.py`、三个前端权限/策略页面、权限测试 |
| Attachment grounding/citation fix | attachment store/context、assistant endpoint/service/prompt、附件页面 scope、关联测试 |
| DeepSeek routing/evaluator fix | OpenAI-compatible adapter、安全 smoke 脚本、AnalysisPlan/adapter 测试、诊断文档 |
| Docs/evidence | `TASK_STATUS.md`、本报告、脱敏真实调用 JSON |

未发现无关产品功能、大规模重构、权限放宽、fallback 假成功、生产模型激活或 RAG production alias 切换。

## 停止边界

- 本报告只关闭 Targeted Gate，不等同于 Final SAME-SHA Full Regression。
- main、Tag、普通根目录、生产 Go-Live、模型 Active 和 RAG production alias 均未改变。
- 下一步只能先提交形成 `REMEDIATION_SHA`，再更新最终 Release 文件形成新的 `FINAL_PRE_RELEASE_SHA`。
