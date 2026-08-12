# AI Assistant Runtime & Multi-Provider V1 Hotfix 报告

## 最终结论

```text
AI_ASSISTANT_RUNTIME_HOTFIX=PARTIAL
LOCAL_PREPRODUCTION_RC=PARTIAL
RELEASE_BLOCKING=2
UNCLASSIFIED_FAIL=0
UNCLASSIFIED_ERROR=0
```

本地/预发布 AI Assistant 的路由、ChatBI、候选 RAG、业务工具、Provider 选择器、DeepSeek、五种回答模式、前端、浏览器、回归与一键启动均已闭环。唯一发布阻断为批准配置中缺少 Kimi、MiMo Key；因此严格按任务标准不宣称 PASS，不创建 RC tag。

- 冻结基线：`day7-final-unified-rc-20260811` / `fefb72f6c56e387a10bd2a4d798813593f1f2334`，保持不变。
- 最终实现 SHA：`85f93fa7b613e0bf4e81948b47bc04501eec6efb`。
- 最终交付 SHA：本报告所在提交，以 `git rev-parse HEAD` 为准（仅追加报告/证据，不改变上述实现树）。
- 分支：`hotfix/ai-assistant-runtime-providers-20260812`。

## 根因与修复

1. 旧路由未先区分 General/ChatBI/RAG/业务分析，普通日期和工具型业务问题也会打开 RAG。现已建立六路由总控，只有 `RAG_QA` 是企业 RAG 硬前置。
2. AnalysisPlan 对 provider wrapper、reasoning、JSON fence、camelCase、tool arguments 兼容不足。现统一规范化，首次校验失败只允许一次定向修复，仍非法则 fail-closed。
3. 预生产 RAG 依赖 production alias，alias 为空时返回 503。现以只读身份直接连接冻结 candidate，并保持 alias 不变。
4. 严格 BGE embedding/reranker 首请求才冷加载，在低内存机器造成长尾超时。现启动时 fail-closed 预热，健康门禁要求 ready，并将可配置默认启动预算提高到 720 秒。
5. “购电策略/政策解读/三类预测”等短问题会落入宽泛兜底意图。现补充精确语义优先级、各自工具链和 unavailable 证据边界。
6. 原运行时仅支持单一模型路径。现建立统一 Provider 协议、显式选择失败不换模型、AUTO 仅对 timeout/429/5xx 回退，并向 UI 返回实际 provider/model。

## 四个失败 Case Before / After

| Case | Before | After |
|---|---|---|
| 解释高价风险原因 | RAG 冷加载/请求超时 | `BUSINESS_ANALYSIS`，业务工具证据 1，RAG=false，HTTP 200 |
| 数据库最新天气数据是哪天 | AnalysisPlan/运行时不稳定 | `CHATBI`，plan valid、结果集与叙事可用，HTTP 200 |
| 对比历史同期情况 | `503 enterprise_rag_runtime_unavailable` | candidate RAG 取回 3 项、证据 6、grounded，HTTP 200 |
| 今天几号 | 被业务域误分类 | 确定性 `GENERAL_CHAT` 快路径，不调用 RAG/LLM，HTTP 200 |

## 四包交付

| Package | 提交 | 状态 | 内容 |
|---|---|---|---|
| 1 | `9f3d2ea` | PASS | Runtime/Routing/AnalysisPlan/Memory 降级/candidate RAG |
| 2 | `bc4b2c2` | PARTIAL | Multi-Provider 适配与 DeepSeek 实测；Kimi/MiMo 缺 Key |
| 3 | `72bcd65` | PASS | 会话级选择器、实际模型标签、五模式、四视口 UI |
| 4 | `1c083c2`、`b567c22`、`84910a2`、`85f93fa` | PARTIAL | E2E、严格 RAG 预热、启动预算、三类预测路由、回归与最终验收 |

每包均有 PRE checkpoint、专项测试与独立提交；Package 4 在真实 E2E 中发现并以三个独立纠正提交关闭长尾问题，没有改写历史提交。

## 最终验收

- AUTO 完整业务矩阵：11/11 PASS、11/11 HTTP 200；详见 `package4/final_route_scenario_matrix.json`。
- DeepSeek `deepseek-v4-flash`：鉴权/模型列表、中文、多轮、流式、结构化、Tools、并发 2、timeout 策略全部 PASS。
- Kimi `kimi-k2.6`、MiMo `mimo-v2.5`：适配与契约测试完成；真实探针因缺 Key 标记 `BLOCKED_MISSING_KEY`。
- ChatBI Golden 50/50；Memory、RAG、Security 守卫 PASS；AI 助手隔离回归 20 passed；定向回归 33 passed。
- 前端构建 PASS（3675 modules），五个模式、四 Provider 选项和四视口浏览器验证 PASS。
- RAG 冷启动 ready：BGE 1024 维、sentence-transformers、BGE reranker，无 fallback；Qdrant 正式 8,339 points，production alias 仍为空。
- `run_project.bat`：实现 SHA 完成冷启动 PASS，并完成连续幂等启动；报告提交后的最终交付 SHA 再连续执行两次。
- 临时 E2E 用户和所有相关业务数据残留 0，审计日志保留。

## 发布边界与回滚

- `PRODUCTION_CUTOVER=NOT_EXECUTED`
- `PRODUCTION_MODEL_ACTIVATION=NOT_EXECUTED`
- `PRODUCTION_RAG_ALIAS_SWITCH=NOT_EXECUTED`
- `REMOTE_PUSH=NOT_EXECUTED`
- `RC_TAG=NOT_CREATED_RELEASE_BLOCKED`

本 Hotfix 无数据库迁移。单包回滚使用 `git revert <package commit>`；整体回滚按 `85f93fa → 84910a2 → b567c22 → 1c083c2 → 72bcd65 → bc4b2c2 → 9f3d2ea` 逆序执行。PRE 检查点均在 `backups/phase3/`。
