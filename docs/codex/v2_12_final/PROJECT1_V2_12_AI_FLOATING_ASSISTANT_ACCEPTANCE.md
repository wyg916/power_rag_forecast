# PROJECT1 v2.12.0 AI Floating Assistant Acceptance

## Round 1 结果

| 验收项 | 结果 |
|---|---|
| 任意业务页 → 悬浮球 → Drawer | PASS |
| forecast → strategy 页面切换 | 会话保持，PASS |
| current page context 更新 | PASS |
| PNG/JPG/PDF/DOCX/XLSX/CSV/TXT file select | PASS |
| Ctrl+V clipboard PNG | PASS |
| upload → parsing → ready → GET | PASS |
| question → answer → citation | PASS |
| DELETE → cannot reuse | PASS（删除后 410） |
| cross-user / cross-tenant | 0 / 0 |
| prompt injection execution | 0；检测到但未执行 |
| hidden-page data access | 0 |
| citation count | 1（验收样本） |

## 诚实边界

- 实际浏览器执行了 clipboard paste 与 file selector。
- 原生操作系统 drag/drop 未在 Round 1 自动化中执行；drag/drop handler 由前端契约测试覆盖。不得把契约覆盖表述成实际 OS 拖放。
- 附件证据中不保存文件正文、凭据、Token 或完整 DSN。
- Provider smoke 为最小真实调用，且保存的是脱敏 trace 元数据，不保存 prompt/answer 正文。

## 路由与 SQL 安全

- `GENERAL_DEFAULT` / `VISION_DEFAULT`：MiMo 路由 PASS。
- `DATA_PLANNER` / `COMPLEX_REASONER`：DeepSeek 路由 PASS。
- `PREMIUM`：仅显式触发 Kimi；未确认时拒绝；静默升级计数 0。
- ChatBI 只接受受控 `AnalysisPlan`，LLM 任意 SQL 执行计数 0。

## 证据

- `round1_floating_ai_browser_4a108ce.json`
- `round1_attachment_lifecycle_4a108ce.json`
- `round1_floating_ai_citation_4a108ce.png`
- `round1_provider_mimo_general_4a108ce.json`
- `round1_provider_mimo_vision_4a108ce.json`
- `round1_provider_deepseek_plan_4a108ce.json`
- `round1_provider_kimi_premium_4a108ce.json`

Round 2 将在 `FINAL_PRE_RELEASE_SHA` 上重新执行同 SHA 门禁。
