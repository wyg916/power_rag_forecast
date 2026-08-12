# Package 4 — Provider E2E / Browser / Regression / Final Acceptance

- 状态：`PARTIAL`
- 实现 SHA：`85f93fa7b613e0bf4e81948b47bc04501eec6efb`
- PRE checkpoint：`backups/phase3/20260812_170100000_AI_ASSISTANT_HOTFIX_PACKAGE4_PRE`
- 未通过原因：本地批准配置中没有 `KIMI_API_KEY`、`MIMO_API_KEY`，两家真实鉴权和能力探针无法执行。

## 最终场景

AUTO 模式完整矩阵 `11/11 PASS`、`11/11 HTTP 200`：日期、解释高价、ChatBI 天气日期、历史同期、分时电价预测、新能源出力预测、负荷预测、购电策略、风险评估、报告、政策解读全部得到正常答案并命中预期产品路由。

- 日期问题走确定性 `GENERAL_CHAT`，不调用 RAG/LLM。
- 高价、预测、策略、风险、报告均由真实业务工具提供证据，不把 RAG 作为硬前置。
- 历史同期和政策解读走 `RAG_QA`，均取回 3 个候选并达到 `grounded`。
- 新能源预测当前未接入时返回明确 unavailable 边界和证据，未生成虚假数值。
- DeepSeek 间歇空响应时，AUTO 如实标记 provider unavailable 并保留可核验工具事实回答，不伪报模型成功。

权威证据：`final_route_scenario_matrix.json`。

## Provider

| Provider | 固定模型 | 最终结果 |
|---|---|---|
| Kimi | `kimi-k2.6` | `BLOCKED_MISSING_KEY` |
| MiMo | `mimo-v2.5` | `BLOCKED_MISSING_KEY` |
| DeepSeek | `deepseek-v4-flash` | PASS：鉴权/模型可见、中文、多轮、流式、结构化、Tools、并发 2、120 秒超时策略 |

权威证据：`provider_live_probe_final.json`。证据仅含不可逆短指纹，不含 Key 或模型回答正文。

## RAG 与启动

- 启动阶段 fail-closed 预热固定 `BAAI/bge-large-zh-v1.5` 1024 维 embedding 与 BGE reranker；健康接口仅在 `status=ready` 后通过。
- 最终实现 SHA 冷启动实测：embedding `248087.268 ms`、reranker `4560.575 ms`，无 hash/fallback。
- 启动器后端默认等待预算由 420 秒调整为 720 秒，仍可通过环境变量覆盖。
- Qdrant 正式集合 `rag_chunks_RAG-R1` 为 8,339 points、1024 维、strict mode；production alias 保持空，写操作 0。
- `84910a2` 连续两次完整 `run_project.bat` PASS；`85f93fa` 冷启动完整 PASS。报告提交后的最终交付 SHA 另执行连续两次幂等启动。

## 回归与 UI

- AI 助手权威隔离回归：`20 passed`；`public_match=true`；临时 schema/role 残留 0。
- Hotfix 定向回归：`33 passed`。
- ChatBI Golden：`50/50 PASS`；Memory、RAG、Security 隔离守卫均 PASS，public 指纹一致且清理 PASS。
- 前端 TypeScript/Vite 构建 PASS，`3675 modules transformed`。
- 五个模式和四 Provider 选择器可用；四视口 1920×1080、1440×900、1366×768、1280×800 无横向溢出，截图在本目录。
- 临时账号 `codex_hotfix_e2e_20260812` 及其会话/消息/状态/工具日志/trace/ChatBI/记忆已精确清理；所有相关 `user_id` 残留 0，审计日志保留。

## 边界与回滚

- 未执行 production cutover、生产模型激活、RAG production alias 切换、远端 push。
- 未新增数据库迁移。回滚时按逆序 `git revert 85f93fa 84910a2 b567c22 1c083c2`；前三包如需整体回滚，再逆序 revert `72bcd65 bc4b2c2 9f3d2ea`。
- 因发布阻断不为 0，不创建 `ai-assistant-runtime-hotfix-rc-20260812` tag。
